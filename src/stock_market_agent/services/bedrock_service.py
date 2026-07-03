from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from stock_market_agent.config import get_settings
from stock_market_agent.services.metrics import estimate_tokens, get_metrics_service
from stock_market_agent.services.observability import get_observability


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
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> str:
        started_at = perf_counter()
        input_tokens = estimate_tokens(prompt) + estimate_tokens(system_prompt)
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
            latency_ms = (perf_counter() - started_at) * 1000
            get_metrics_service().record_llm_call(
                provider="bedrock",
                model_id=self.settings.bedrock_chat_model_id,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            get_observability().record_model_call(
                name=prompt_name or "bedrock_generation",
                model_id=self.settings.bedrock_chat_model_id,
                input_payload={"prompt": prompt, "system_prompt": system_prompt},
                output_payload=None,
                input_tokens=input_tokens,
                output_tokens=0,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                model_parameters={"max_tokens": max_tokens, "temperature": temperature},
                success=False,
                error=str(exc),
                observation_type="generation",
            )
            return f"Bedrock generation unavailable: {exc}"

        content = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        answer = "\n".join(part for part in text_parts if part).strip()
        usage = response.get("usage", {})
        output_tokens = int(usage.get("outputTokens") or estimate_tokens(answer))
        measured_input_tokens = int(usage.get("inputTokens") or input_tokens)
        latency_ms = (perf_counter() - started_at) * 1000
        get_metrics_service().record_llm_call(
            provider="bedrock",
            model_id=self.settings.bedrock_chat_model_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            input_tokens=measured_input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            success=True,
        )
        get_observability().record_model_call(
            name=prompt_name or "bedrock_generation",
            model_id=self.settings.bedrock_chat_model_id,
            input_payload={"prompt": prompt, "system_prompt": system_prompt},
            output_payload=answer,
            input_tokens=measured_input_tokens,
            output_tokens=output_tokens,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            success=True,
            observation_type="generation",
        )
        return answer

    def embed_text(self, text: str) -> list[float]:
        started_at = perf_counter()
        input_tokens = estimate_tokens(text)
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
        except (BotoCoreError, ClientError, Exception) as exc:
            latency_ms = (perf_counter() - started_at) * 1000
            get_metrics_service().record_llm_call(
                provider="bedrock",
                model_id=self.settings.bedrock_embedding_model_id,
                prompt_name="embedding",
                prompt_version=None,
                input_tokens=input_tokens,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )
            get_observability().record_model_call(
                name="embedding",
                model_id=self.settings.bedrock_embedding_model_id,
                input_payload=text,
                output_payload=None,
                input_tokens=input_tokens,
                output_tokens=0,
                prompt_name="embedding",
                prompt_version=None,
                model_parameters={"dimensions": 1024, "normalize": True},
                success=False,
                error=str(exc),
                observation_type="embedding",
            )
            return []

        embedding = payload.get("embedding")
        if isinstance(embedding, list):
            latency_ms = (perf_counter() - started_at) * 1000
            get_metrics_service().record_llm_call(
                provider="bedrock",
                model_id=self.settings.bedrock_embedding_model_id,
                prompt_name="embedding",
                prompt_version=None,
                input_tokens=input_tokens,
                output_tokens=0,
                latency_ms=latency_ms,
                success=True,
            )
            get_observability().record_model_call(
                name="embedding",
                model_id=self.settings.bedrock_embedding_model_id,
                input_payload=text,
                output_payload={"embedding_dimensions": len(embedding)},
                input_tokens=input_tokens,
                output_tokens=0,
                prompt_name="embedding",
                prompt_version=None,
                model_parameters={"dimensions": 1024, "normalize": True},
                success=True,
                observation_type="embedding",
            )
            return [float(value) for value in embedding]
        return []
