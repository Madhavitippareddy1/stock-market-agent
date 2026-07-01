from stock_market_agent.config import Settings
from stock_market_agent.services.metrics import MetricsService, estimate_bedrock_cost


def test_metrics_service_summarizes_requests_and_llm_calls(tmp_path):
    service = MetricsService(Settings(observability_metrics_path=str(tmp_path / "metrics.jsonl")))

    service.record_request(
        question="compare Apple and Meta",
        user_id="demo-user",
        agent="Stock Agent",
        route="stock",
        latency_ms=100,
        success=True,
    )
    service.record_llm_call(
        provider="bedrock",
        model_id="amazon.nova-lite-v1:0",
        prompt_name="investment_research_summary",
        prompt_version="v1.0.0",
        input_tokens=1000,
        output_tokens=500,
        latency_ms=200,
        success=True,
    )

    summary = service.dashboard_summary()

    assert summary["request_count"] == 1
    assert summary["llm_call_count"] == 1
    assert summary["total_tokens"] == 1500
    assert summary["avg_cost_per_request"] > 0


def test_bedrock_cost_estimate_is_non_zero_for_nova_lite():
    assert estimate_bedrock_cost(
        model_id="amazon.nova-lite-v1:0",
        input_tokens=1000,
        output_tokens=1000,
    ) > 0
