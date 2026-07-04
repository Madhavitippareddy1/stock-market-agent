from stock_market_agent.config import Settings
from stock_market_agent.services.observability import (
    LangfuseObservability,
    RagasEvaluationService,
)


def test_ragas_evaluator_returns_expected_scores():
    settings = Settings(
        ragas_enabled=True,
        ragas_score_prefix="ragas",
        ragas_min_context_precision=0.0,
        ragas_min_faithfulness=0.0,
    )
    evaluator = RagasEvaluationService(settings)

    result = evaluator.evaluate(
        question="Apple revenue and net income report",
        answer="Apple revenue increased and net income improved according to the report.",
        contexts=[
            "Apple annual report shows revenue increased. Net income improved year over year."
        ],
    )

    score_names = {score.name for score in result.scores}
    assert result.passed is True
    assert "ragas_context_precision" in score_names
    assert "ragas_answer_relevancy" in score_names
    assert "ragas_faithfulness" in score_names
    assert "ragas_context_recall" in score_names
    assert all(0 <= score.value <= 1 for score in result.scores)


def test_ragas_evaluator_can_be_disabled():
    evaluator = RagasEvaluationService(Settings(ragas_enabled=False))

    result = evaluator.evaluate(question="test", answer="test", contexts=["test"])

    assert result.evaluator == "disabled"
    assert result.scores == []
    assert result.passed is True


def test_langfuse_observability_disabled_without_credentials():
    observability = LangfuseObservability(
        Settings(
            langfuse_enabled=True,
            langfuse_public_key=None,
            langfuse_secret_key=None,
        )
    )

    assert observability.enabled is False
    with observability.trace_agent_run(
        name="test",
        question="hello",
        user_id="demo-user",
    ) as span:
        assert span is None

class FakeLangfuseObservation:
    def __init__(self):
        self.updated = None
        self.ended = False
        self.scores = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.ended = True
        return False

    def update(self, **kwargs):
        self.updated = kwargs
        return self

    def end(self):
        self.ended = True
        return self

    def score(self, **kwargs):
        self.scores.append(kwargs)


class FakeLangfuseClient:
    def __init__(self):
        self.started = None
        self.observation = FakeLangfuseObservation()

    def start_as_current_observation(self, **kwargs):
        self.started = kwargs
        return self.observation


def test_langfuse_model_call_records_usage_and_cost_details():
    observability = LangfuseObservability(Settings(langfuse_enabled=False))
    fake_client = FakeLangfuseClient()
    observability.enabled = True
    observability._client = fake_client

    observability.record_model_call(
        name="investment_research_summary",
        model_id="amazon.nova-lite-v1:0",
        input_payload={"prompt": "hello"},
        output_payload="answer",
        input_tokens=1000,
        output_tokens=500,
        prompt_name="investment_research_summary",
        prompt_version="v1.2.0",
        model_parameters={"temperature": 0.15, "max_tokens": 800},
    )

    assert fake_client.started["as_type"] == "generation"
    assert fake_client.started["model"] == "amazon.nova-lite-v1:0"
    assert fake_client.started["usage_details"] == {"input": 1000, "output": 500, "total": 1500}
    assert fake_client.started["cost_details"]["total"] > 0
    assert fake_client.started["metadata"]["prompt_version"] == "v1.2.0"
    assert fake_client.observation.updated["usage_details"]["total"] == 1500
    assert any(score["name"] == "model_cost_usd" for score in fake_client.observation.scores)
    assert fake_client.observation.ended is True
