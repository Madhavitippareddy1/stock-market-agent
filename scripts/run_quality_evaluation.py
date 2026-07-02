from __future__ import annotations

import argparse
import json
from pathlib import Path

from stock_market_agent.services.evaluation import (
    GoldenExample,
    grade_agent_result,
    load_golden_dataset,
    summarize_evaluation,
    trajectory_grade,
)


def dry_run_result(example: GoldenExample) -> dict:
    """Cheap CI-safe result used to verify dataset and evaluator wiring."""

    answer_terms = ", ".join(example.expected_terms)
    data = {}
    if example.expected_tool:
        data["tool"] = example.expected_tool
    if example.expected_prompt:
        data["prompt"] = example.expected_prompt
    elif example.expected_agent == "Investment Agent":
        data["prompt"] = {"name": "investment_research_summary", "version": "v1.0.0"}

    return {
        "agent": example.expected_agent,
        "answer": f"Dry-run expected answer for {example.question}. Key terms: {answer_terms}.",
        "sources": ["golden-dataset://dry-run"],
        "data": data,
    }


def run(mode: str, output_path: Path) -> dict:
    examples = load_golden_dataset()
    rows = []
    trajectory_rows = []
    if mode != "dry-run":
        raise ValueError("Only dry-run mode is enabled for CI-safe evaluation.")

    for example in examples:
        result = dry_run_result(example)
        rows.append(grade_agent_result(example, result))
        trajectory_rows.append(trajectory_grade(example, result))

    payload = {
        "mode": mode,
        "golden_summary": summarize_evaluation(rows),
        "trajectory_summary": summarize_evaluation(trajectory_rows),
        "golden_results": rows,
        "trajectory_results": trajectory_rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stock Market Agent quality evaluation.")
    parser.add_argument("--mode", default="dry-run", choices=["dry-run"])
    parser.add_argument(
        "--output",
        default="data/evaluation/latest_quality_report.json",
        help="Path for JSON evaluation report.",
    )
    args = parser.parse_args()
    report = run(args.mode, Path(args.output))
    print(json.dumps({k: report[k] for k in ["mode", "golden_summary", "trajectory_summary"]}, indent=2))


if __name__ == "__main__":
    main()
