from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_market_agent.config import Settings, get_settings


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    text: str
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None

    def render(self, **values: Any) -> str:
        return self.text.format(**{key: value or "" for key, value in values.items()})


class PromptCatalog:
    """Versioned JSON prompt catalogue.

    Prompts are not hard-coded in agents. The app loads the active prompt version
    from `data/prompts/prompts.json`, which can be version controlled and changed
    without editing agent code.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = Path(self.settings.prompt_catalog_path)
        self._payload: dict[str, Any] | None = None

    def get(self, prompt_name: str, version: str | None = None) -> PromptTemplate:
        payload = self._load()
        prompt = payload["prompts"][prompt_name]
        active_version = version or prompt.get("active_version")
        versions = {item["version"]: item for item in prompt.get("versions", [])}
        if active_version not in versions:
            raise KeyError(f"Prompt {prompt_name!r} version {active_version!r} was not found.")
        selected = versions[active_version]
        return PromptTemplate(
            name=prompt_name,
            version=active_version,
            text=selected["template"],
            system_prompt=selected.get("system_prompt"),
            metadata=selected.get("metadata", {}),
        )

    def active_versions(self) -> dict[str, str]:
        payload = self._load()
        return {
            name: definition.get("active_version", "")
            for name, definition in payload.get("prompts", {}).items()
        }

    def _load(self) -> dict[str, Any]:
        if self._payload is not None:
            return self._payload
        with self.path.open("r", encoding="utf-8") as handle:
            self._payload = json.load(handle)
        return self._payload


_catalog: PromptCatalog | None = None


def get_prompt_catalog() -> PromptCatalog:
    global _catalog
    if _catalog is None:
        _catalog = PromptCatalog()
    return _catalog
