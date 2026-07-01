from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoldenExample:
    id: str
    category: str
    question: str
    expected_agent: str
    expected_terms: list[str]


def load_golden_dataset(path: str | Path = "data/evaluation/golden_dataset.json") -> list[GoldenExample]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        GoldenExample(
            id=item["id"],
            category=item["category"],
            question=item["question"],
            expected_agent=item["expected_agent"],
            expected_terms=item.get("expected_terms", []),
        )
        for item in payload["examples"]
    ]


def grade_agent_result(example: GoldenExample, result: dict[str, Any]) -> dict[str, Any]:
    actual_agent = result.get("agent", "")
    answer = str(result.get("answer", ""))
    answer_lower = answer.lower()
    matched_terms = [
        term for term in example.expected_terms if term.lower() in answer_lower
    ]
    agent_match = actual_agent == example.expected_agent
    term_coverage = len(matched_terms) / len(example.expected_terms) if example.expected_terms else 1.0
    score = (0.65 if agent_match else 0.0) + (0.35 * term_coverage)
    return {
        "id": example.id,
        "category": example.category,
        "question": example.question,
        "expected_agent": example.expected_agent,
        "actual_agent": actual_agent,
        "agent_match": agent_match,
        "expected_terms": example.expected_terms,
        "matched_terms": matched_terms,
        "term_coverage": round(term_coverage, 4),
        "score": round(score, 4),
        "passed": score >= 0.75,
        "method": "golden-dataset-answer-check",
    }


def trajectory_grade(example: GoldenExample, result: dict[str, Any]) -> dict[str, Any]:
    """Additional evaluation method beyond RAGAS.

    This grades whether the supervisor selected the expected specialist agent and
    whether the trajectory metadata is present. It is intentionally deterministic
    so CI can run it without LLM cost.
    """

    data = result.get("data", {}) or {}
    has_sources = bool(result.get("sources"))
    has_prompt_version = bool(data.get("prompt"))
    score = 0.0
    reasons: list[str] = []
    if result.get("agent") == example.expected_agent:
        score += 0.7
        reasons.append("selected expected agent")
    else:
        reasons.append("selected different agent")

    if has_sources or example.expected_agent in {"User Agent", "Portfolio Agent", "Investment Agent"}:
        score += 0.15
        reasons.append("trajectory has sources or agent context")
    if has_prompt_version or example.expected_agent != "Investment Agent":
        score += 0.15
        reasons.append("prompt version present when required")

    return {
        "id": example.id,
        "method": "trajectory-grading",
        "score": round(min(score, 1.0), 4),
        "passed": score >= 0.7,
        "reasons": reasons,
    }


def summarize_evaluation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "pass_rate": 0.0, "average_score": 0.0}
    return {
        "count": len(rows),
        "passed": sum(1 for row in rows if row.get("passed")),
        "pass_rate": round(sum(1 for row in rows if row.get("passed")) / len(rows), 4),
        "average_score": round(sum(float(row.get("score", 0)) for row in rows) / len(rows), 4),
    }
