from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urljoin

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials

from stock_market_agent.config import Settings


@dataclass
class RagSearchResult:
    answer: str
    sources: list[str]
    chunks: list[dict]


class OpenSearchRagService:
    """Small AWS-native RAG helper using Bedrock embeddings + OpenSearch Serverless."""

    def __init__(self, settings: Settings) -> None:
        self.endpoint = (settings.opensearch_endpoint or "").rstrip("/")
        self.index_name = settings.opensearch_index
        self.region = settings.aws_region
        self.embedding_model_id = settings.bedrock_embedding_model_id
        self.bedrock = boto3.client("bedrock-runtime", region_name=self.region)
        self.session = boto3.Session(region_name=self.region)

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.index_name)

    def search(self, question: str, top_k: int = 5) -> RagSearchResult:
        if not self.enabled:
            return RagSearchResult(answer="", sources=[], chunks=[])

        embedding = self.embed(question)
        payload = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": top_k,
                    }
                }
            },
            "_source": ["ticker", "source", "text", "s3_uri", "period"],
        }
        response = self.signed_request(
            "POST",
            f"/{self.index_name}/_search",
            payload,
        )
        hits = response.get("hits", {}).get("hits", [])
        chunks = [
            {
                "score": hit.get("_score"),
                **(hit.get("_source") or {}),
            }
            for hit in hits
        ]
        sources = list(
            dict.fromkeys(
                item.get("s3_uri") or item.get("source")
                for item in chunks
                if item.get("s3_uri") or item.get("source")
            )
        )
        answer = build_rag_answer(question, chunks)
        return RagSearchResult(answer=answer, sources=sources, chunks=chunks)

    def embed(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text})
        response = self.bedrock.invoke_model(
            modelId=self.embedding_model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read())
        return payload.get("embedding") or payload.get("embeddings", [{}])[0].get("embedding", [])

    def signed_request(self, method: str, path: str, payload: dict) -> dict:
        url = urljoin(self.endpoint + "/", path.lstrip("/"))
        body = json.dumps(payload)
        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("AWS credentials are not available for OpenSearch request.")
        frozen = credentials.get_frozen_credentials()
        readonly = ReadOnlyCredentials(
            frozen.access_key,
            frozen.secret_key,
            frozen.token,
        )
        request = AWSRequest(
            method=method,
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(readonly, "aoss", self.region).add_auth(request)
        prepared = request.prepare()
        response = requests.request(
            method,
            url,
            data=body,
            headers=dict(prepared.headers),
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


def build_rag_answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return (
            "No relevant OpenSearch financial-report chunks were found. "
            "Try asking for one of the NASDAQ-10 tickers or upload a report."
        )

    lines = [
        "OpenSearch RAG financial report answer",
        "",
        f"Question: {question}",
        "",
        "Retrieved evidence:",
    ]
    for item in chunks[:5]:
        ticker = item.get("ticker", "unknown")
        text = (item.get("text") or "").replace("\n", " ").strip()
        lines.append(f"- {ticker}: {text[:450]}")
    lines.extend(
        [
            "",
            "Summary:",
            (
                "The answer is grounded in the retrieved S3 financial report chunks. "
                "Use this for educational research only, not investment advice."
            ),
        ]
    )
    return "\n".join(lines)
