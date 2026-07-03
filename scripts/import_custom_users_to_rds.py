from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_market_agent.services.local_market_data import (
    _load_custom_store,
    _save_custom_store,
)


def merge_custom_store(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "users": dict(existing.get("users", {})),
        "portfolios": dict(existing.get("portfolios", {})),
    }
    for user_id, user in incoming.get("users", {}).items():
        merged["users"][user_id] = user
    for user_id, holdings in incoming.get("portfolios", {}).items():
        merged["portfolios"][user_id] = holdings
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Import custom Streamlit users into the configured RDS store.")
    parser.add_argument(
        "--file",
        default="data/custom_users.json",
        help="Path to the local custom_users.json file.",
    )
    args = parser.parse_args()

    source_path = Path(args.file)
    if not source_path.exists():
        raise SystemExit(f"Custom users file was not found: {source_path}")

    incoming = json.loads(source_path.read_text(encoding="utf-8"))
    existing = _load_custom_store()
    merged = merge_custom_store(existing, incoming)
    _save_custom_store(merged)

    print(
        json.dumps(
            {
                "status": "imported",
                "source_file": str(source_path),
                "imported_users": sorted(incoming.get("users", {}).keys()),
                "imported_portfolios": sorted(incoming.get("portfolios", {}).keys()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
