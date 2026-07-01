from stock_market_agent.services.evaluation import (
    grade_agent_result,
    load_golden_dataset,
    trajectory_grade,
)


def test_golden_dataset_has_required_minimum_examples():
    examples = load_golden_dataset()

    assert len(examples) >= 20
    assert {example.category for example in examples} >= {
        "stock_price",
        "rag",
        "portfolio",
        "investment",
    }


def test_golden_answer_and_trajectory_grading_pass_for_expected_result():
    example = load_golden_dataset()[0]
    result = {
        "agent": example.expected_agent,
        "answer": " ".join(example.expected_terms),
        "sources": ["test://source"],
        "data": {"prompt": {"name": "test", "version": "v1"}},
    }

    assert grade_agent_result(example, result)["passed"] is True
    assert trajectory_grade(example, result)["passed"] is True
