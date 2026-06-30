from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from stock_market_agent.config import get_settings


class BedrockService:
    """Small Amazon Bedrock adapter for generation and embeddings.

    Generation uses Bedrock Converse, configured for Amazon Nova Lite by default.
    Embeddings use Amazon Titan Text Embeddings V2 by default.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.settings = get_settings()
        self.client = client or boto3.client("bedrock-runtime", region_name=self.settings.aws_region)

    def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs: dict[str, Any] = {
            "modelId": self.settings.bedrock_chat_model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]

        try:
            response = self.client.converse(**kwargs)
        except (BotoCoreError, ClientError, Exception) as exc:
            return f"Bedrock generation unavailable: {exc}"

        content = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "\n".join(part for part in text_parts if part).strip()

    def embed_text(self, text: str) -> list[float]:
        body = {
            "inputText": text,
            "dimensions": 1024,
            "normalize": True,
        }

        try:
            response = self.client.invoke_model(
                modelId=self.settings.bedrock_embedding_model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            payload = json.loads(response["body"].read())
        except (BotoCoreError, ClientError, Exception):
            return []

        embedding = payload.get("embedding")
        if isinstance(embedding, list):
            return [float(value) for value in embedding]
        return []
