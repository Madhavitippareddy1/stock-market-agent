from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from langfuse import get_client

DEFAULT_PROMPT_CATALOG = Path("data/prompts/prompts.json")


def _labels_for_version(version: str, active_version: str, environment: str) -> list[str]:
    labels = [version]
    if version == active_version:
        labels.extend(["latest", environment])
    return labels


def _chat_prompt(system_prompt: str | None, template: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": template})
    return messages


def _prompt_exists(client: Any, name: str, label: str) -> bool:
    try:
        client.get_prompt(name, label=label, type="chat", cache_ttl_seconds=0)
        return True
    except Exception:
        return False


def publish_prompts(
    *,
    catalog_path: Path = DEFAULT_PROMPT_CATALOG,
    environment: str = "production",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    client = None if dry_run else get_client()
    results: list[dict[str, Any]] = []

    for prompt_name, prompt_definition in payload.get("prompts", {}).items():
        active_version = prompt_definition.get("active_version", "")
        for version_definition in prompt_definition.get("versions", []):
            semantic_version = version_definition["version"]
            langfuse_name = f"stock-market-agent/{prompt_name}"
            labels = _labels_for_version(semantic_version, active_version, environment)
            exists = False if dry_run else _prompt_exists(client, langfuse_name, semantic_version)
            action = "exists" if exists else "create"

            config = {
                "semantic_version": semantic_version,
                "active_version": active_version,
                "environment": environment,
                "owner": version_definition.get("owner", "stock-market-agent"),
                "created_at": version_definition.get("created_at"),
                "description": prompt_definition.get("description"),
                **(version_definition.get("metadata") or {}),
            }

            if not dry_run and not exists:
                client.create_prompt(
                    name=langfuse_name,
                    prompt=_chat_prompt(
                        version_definition.get("system_prompt"),
                        version_definition["template"],
                    ),
                    labels=labels,
                    tags=["stock-market-agent", prompt_name, semantic_version],
                    type="chat",
                    config=config,
                    commit_message=(
                        f"Publish {prompt_name} {semantic_version} from "
                        f"{catalog_path.as_posix()}"
                    ),
                )

            results.append(
                {
                    "name": langfuse_name,
                    "semantic_version": semantic_version,
                    "labels": labels,
                    "action": action,
                }
            )

    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish local prompt catalogue versions to Langfuse Prompt Management."
    )
    parser.add_argument(
        "--catalog",
        default=os.getenv("PROMPT_CATALOG_PATH", str(DEFAULT_PROMPT_CATALOG)),
        help="Path to data/prompts/prompts.json.",
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("ACTIVE_PROMPT_ENVIRONMENT", "production"),
        help="Label added to active prompt versions, for example production or staging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned prompt publishing actions without calling Langfuse.",
    )
    args = parser.parse_args()

    missing = [
        key
        for key in ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"]
        if not os.getenv(key)
    ]
    if missing and not args.dry_run:
        raise SystemExit(
            "Missing Langfuse environment variables: "
            + ", ".join(missing)
            + ". Set them or run with --dry-run."
        )

    results = publish_prompts(
        catalog_path=Path(args.catalog),
        environment=args.environment,
        dry_run=args.dry_run,
    )
    for result in results:
        print(
            f"{result['action']}: {result['name']} "
            f"{result['semantic_version']} labels={','.join(result['labels'])}"
        )


if __name__ == "__main__":
    main()