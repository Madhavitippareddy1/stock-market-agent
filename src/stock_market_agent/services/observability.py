from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from stock_market_agent.config import Settings, get_settings


@dataclass
class RagasScore:
    """Small score object compatible with Langfuse numeric score ingestion."""

    name: str
    value: float
    comment: str = ""


@dataclass
class RagasEvaluation:
    """RAG quality scores exposed in agent data and sent to Langfuse."""

    scores: list[RagasScore] = field(default_factory=list)
    passed: bool = True
    evaluator: str = "deterministic-ragas-compatible"

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "passed": self.passed,
            "scores": [
                {"name": score.name, "value": round(score.value, 4), "comment": score.comment}
                for score in self.scores
            ],
        }


def _terms(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "report",
        "stock",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9.-]+", text)
        if token.lower() not in stop_words and len(token) > 2
    }


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


class RagasEvaluationService:
    """RAGAS-style evaluator for retrieved-context RAG responses.

    The project installs `ragas`, but production RAGAS LLM-as-judge evaluation can add
    latency and model cost. This deterministic evaluator uses the same operational score
    categories that teams expect from RAGAS dashboards:

    - context precision: how much retrieved context overlaps the question
    - answer relevancy: how much the answer addresses the question terms
    - faithfulness: how much answer content is supported by retrieved context
    - context recall proxy: how much question terminology is covered by context
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> RagasEvaluation:
        if not self.settings.ragas_enabled:
            return RagasEvaluation(scores=[], passed=True, evaluator="disabled")

        question_terms = _terms(question)
        answer_terms = _terms(answer)
        context_text = " ".join(contexts)
        context_terms = _terms(context_text)
        ground_truth_terms = _terms(ground_truth or "")

        context_precision = _safe_ratio(len(question_terms & context_terms), len(context_terms))
        answer_relevancy = _safe_ratio(len(question_terms & answer_terms), len(question_terms))
        faithfulness = self._faithfulness(answer, context_text)
        if ground_truth_terms:
            context_recall = _safe_ratio(len(ground_truth_terms & context_terms), len(ground_truth_terms))
            recall_comment = "Coverage of provided ground-truth terms by retrieved context."
        else:
            context_recall = _safe_ratio(len(question_terms & context_terms), len(question_terms))
            recall_comment = "Proxy recall: coverage of question terms by retrieved context."

        prefix = self.settings.ragas_score_prefix.rstrip("_")
        scores = [
            RagasScore(
                name=f"{prefix}_context_precision",
                value=context_precision,
                comment="Question-term overlap divided by retrieved context vocabulary.",
            ),
            RagasScore(
                name=f"{prefix}_answer_relevancy",
                value=answer_relevancy,
                comment="Question-term coverage in final answer.",
            ),
            RagasScore(
                name=f"{prefix}_faithfulness",
                value=faithfulness,
                comment="Sentence support proxy based on overlap with retrieved contexts.",
            ),
            RagasScore(
                name=f"{prefix}_context_recall",
                value=context_recall,
                comment=recall_comment,
            ),
        ]
        passed = (
            context_precision >= self.settings.ragas_min_context_precision
            and faithfulness >= self.settings.ragas_min_faithfulness
        )
        return RagasEvaluation(scores=scores, passed=passed)

    def _faithfulness(self, answer: str, context_text: str) -> float:
        context_terms = _terms(context_text)
        answer_sentences = _sentences(answer)
        if not answer_sentences:
            return 0.0

        supported = 0
        considered = 0
        for sentence in answer_sentences:
            sentence_terms = _terms(sentence)
            if not sentence_terms:
                continue
            considered += 1
            overlap = _safe_ratio(len(sentence_terms & context_terms), len(sentence_terms))
            if overlap >= 0.25:
                supported += 1
        return _safe_ratio(supported, considered or len(answer_sentences))


class LangfuseObservability:
    """Thin wrapper around Langfuse SDK with safe no-op behavior."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.enabled = bool(
            self.settings.langfuse_enabled
            and self.settings.langfuse_public_key
            and self.settings.langfuse_secret_key
        )
        self._client: Any | None = None
        if self.enabled:
            os.environ.setdefault("LANGFUSE_PUBLIC_KEY", self.settings.langfuse_public_key or "")
            os.environ.setdefault("LANGFUSE_SECRET_KEY", self.settings.langfuse_secret_key or "")
            os.environ.setdefault("LANGFUSE_BASE_URL", self.settings.langfuse_base_url)
            try:
                from langfuse import get_client

                self._client = get_client()
            except Exception:
                self.enabled = False
                self._client = None

    @contextlib.contextmanager
    def trace_agent_run(
        self,
        *,
        name: str,
        question: str,
        user_id: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any | None]:
        if not self.enabled or self._client is None:
            yield None
            return

        span_cm = self._client.start_as_current_observation(
            as_type="span",
            name=name,
            input={"question": question, "user_id": user_id},
            metadata=metadata or {},
        )
        try:
            with span_cm as span:
                try:
                    span.update_trace(
                        user_id=user_id,
                        session_id=session_id or user_id,
                        tags=["stock-market-agent", "aws", "mcp", "ragas"],
                        metadata=metadata or {},
                    )
                except Exception:
                    pass
                yield span
        finally:
            if self.settings.langfuse_flush_on_request:
                self.flush()

    def update_span_output(self, span: Any | None, output: Any) -> None:
        if span is None:
            return
        try:
            span.update(output=output)
            span.score_trace(
                name="agent_latency_ms",
                value=0.0,
                data_type="NUMERIC",
                comment="Latency placeholder; detailed latency is captured by Langfuse span timing.",
            )
        except Exception:
            pass

    def score_current_trace(self, evaluation: RagasEvaluation) -> None:
        if not self.enabled or self._client is None:
            return
        for score in evaluation.scores:
            try:
                self._client.score_current_trace(
                    name=score.name,
                    value=float(score.value),
                    data_type="NUMERIC",
                    comment=score.comment,
                )
            except Exception:
                continue
        try:
            self._client.score_current_trace(
                name="ragas_passed",
                value=1 if evaluation.passed else 0,
                data_type="BOOLEAN",
                comment=f"Evaluator: {evaluation.evaluator}",
            )
        except Exception:
            pass

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception:
            pass


_observability: LangfuseObservability | None = None
_ragas: RagasEvaluationService | None = None


def get_observability() -> LangfuseObservability:
    global _observability
    if _observability is None:
        _observability = LangfuseObservability()
    return _observability


def get_ragas_evaluator() -> RagasEvaluationService:
    global _ragas
    if _ragas is None:
        _ragas = RagasEvaluationService()
    return _ragas
