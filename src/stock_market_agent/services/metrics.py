from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from stock_market_agent.config import Settings, get_settings


NOVA_LITE_INPUT_PER_1K = 0.00006
NOVA_LITE_OUTPUT_PER_1K = 0.00024
TITAN_EMBED_PER_1K = 0.00002


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.35))


def estimate_bedrock_cost(
    *,
    model_id: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> float:
    model = model_id.lower()
    if "nova-lite" in model:
        return (input_tokens / 1000 * NOVA_LITE_INPUT_PER_1K) + (
            output_tokens / 1000 * NOVA_LITE_OUTPUT_PER_1K
        )
    if "embed" in model or "titan" in model:
        return input_tokens / 1000 * TITAN_EMBED_PER_1K
    return 0.0


@dataclass
class RequestTimer:
    service: "MetricsService"
    question: str
    user_id: str
    started_at: float

    def finish(
        self,
        *,
        agent: str,
        route: str | None,
        success: bool,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.service.record_request(
            question=self.question,
            user_id=self.user_id,
            agent=agent,
            route=route,
            latency_ms=(perf_counter() - self.started_at) * 1000,
            success=success,
            error=error,
            metadata=metadata,
        )


class MetricsService:
    """Append-only JSONL metrics store for Streamlit dashboard and CI evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(self.settings.observability_metrics_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def start_request(self, *, question: str, user_id: str) -> RequestTimer:
        return RequestTimer(
            service=self,
            question=question,
            user_id=user_id,
            started_at=perf_counter(),
        )

    def record_request(
        self,
        *,
        question: str,
        user_id: str,
        agent: str,
        route: str | None,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._append(
            {
                "event_type": "request",
                "timestamp": utc_now_iso(),
                "question": question[:500],
                "user_id": user_id,
                "agent": agent,
                "route": route,
                "latency_ms": round(latency_ms, 2),
                "success": success,
                "error": error,
                "metadata": metadata or {},
            }
        )

    def record_llm_call(
        self,
        *,
        provider: str,
        model_id: str,
        prompt_name: str | None,
        prompt_version: str | None,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        success: bool,
        cost_usd: float | None = None,
        error: str | None = None,
    ) -> None:
        if cost_usd is None:
            cost_usd = estimate_bedrock_cost(
                model_id=model_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        self._append(
            {
                "event_type": "llm_call",
                "timestamp": utc_now_iso(),
                "provider": provider,
                "model_id": model_id,
                "prompt_name": prompt_name,
                "prompt_version": prompt_version,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "latency_ms": round(latency_ms, 2),
                "success": success,
                "cost_usd": round(cost_usd, 8),
                "error": error,
            }
        )

    def read_events(self, limit: int = 1000) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def dashboard_summary(self, limit: int = 1000) -> dict[str, Any]:
        events = self.read_events(limit)
        requests = [event for event in events if event.get("event_type") == "request"]
        llm_calls = [event for event in events if event.get("event_type") == "llm_call"]
        latencies = [float(event.get("latency_ms", 0)) for event in requests]
        errors = [event for event in requests if not event.get("success", True)]
        costs = [float(event.get("cost_usd", 0)) for event in llm_calls]
        tokens = [int(event.get("total_tokens", 0)) for event in llm_calls]

        return {
            "request_count": len(requests),
            "llm_call_count": len(llm_calls),
            "error_count": len(errors),
            "error_rate": (len(errors) / len(requests)) if requests else 0.0,
            "avg_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "p50_latency_ms": percentile(latencies, 50),
            "p95_latency_ms": percentile(latencies, 95),
            "total_tokens": sum(tokens),
            "avg_tokens_per_llm_call": statistics.fmean(tokens) if tokens else 0.0,
            "total_cost_usd": sum(costs),
            "avg_cost_per_request": (sum(costs) / len(requests)) if requests else 0.0,
            "last_event_timestamp": events[-1].get("timestamp") if events else None,
            "events": events,
        }

    def _append(self, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (p / 100)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


_metrics: MetricsService | None = None


def get_metrics_service() -> MetricsService:
    global _metrics
    if _metrics is None:
        _metrics = MetricsService()
    return _metrics
