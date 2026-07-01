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
