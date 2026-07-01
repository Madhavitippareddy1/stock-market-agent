from __future__ import annotations

import io
import re
from typing import Any

import boto3
from pypdf import PdfReader

from stock_market_agent.models import AgentResult
from stock_market_agent.config import get_settings
from stock_market_agent.services.mcp_client import McpClient
from stock_market_agent.services.observability import get_observability, get_ragas_evaluator
from stock_market_agent.services.opensearch_rag import OpenSearchRagService


class RagAgent:
    def __init__(self, mcp_client: McpClient) -> None:
        self.mcp_client = mcp_client
        self.settings = get_settings()
        self.opensearch_rag = OpenSearchRagService(self.settings)

    def answer(self, question: str, uploaded_file: Any | None = None) -> AgentResult:
        if uploaded_file is not None:
            return self._answer_uploaded_document(question, uploaded_file)

        if self.opensearch_rag.enabled:
            try:
                rag_result = self.opensearch_rag.search(question)
                if rag_result.chunks:
                    contexts = [str(chunk.get("text", "")) for chunk in rag_result.chunks]
                    evaluation = get_ragas_evaluator().evaluate(
                        question=question,
                        answer=rag_result.answer,
                        contexts=contexts,
                    )
                    get_observability().score_current_trace(evaluation)
                    return AgentResult(
                        agent="RAG Agent",
                        answer=rag_result.answer,
                        sources=rag_result.sources,
                        data={
                            "retrieved_chunks": rag_result.chunks,
                            "ragas": evaluation.as_dict(),
                        },
                    )
            except Exception as exc:
                # Fall back to MCP RAG so the UI still responds if OpenSearch is not ready.
                opensearch_error = str(exc)
            else:
                opensearch_error = ""
        else:
            opensearch_error = ""

        s3_result = self._answer_s3_report(question)
        if s3_result is not None:
            return s3_result

        payload: dict[str, Any] = {"question": question}

        result = self.mcp_client.call_tool("financial_report_research", payload)
        answer = result.get("answer") or "RAG tool did not return an answer yet."
        return AgentResult(
            agent="RAG Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )

    def _answer_uploaded_document(self, question: str, uploaded_file: Any) -> AgentResult:
        document_text = extract_uploaded_file_text(uploaded_file)
        if not document_text.strip():
            return AgentResult(
                agent="RAG Agent",
                answer=(
                    "I could not extract readable text from the uploaded file. "
                    "Please upload a text-based PDF, TXT, or MD financial report."
                ),
                sources=[f"uploaded://{uploaded_file.name}"],
                data={"filename": uploaded_file.name, "chunks": []},
            )

        chunks = chunk_text(document_text)
        selected_chunks = retrieve_relevant_chunks(question, chunks)
        answer = build_grounded_report_answer(question, uploaded_file.name, selected_chunks)
        evaluation = get_ragas_evaluator().evaluate(
            question=question,
            answer=answer,
            contexts=selected_chunks,
        )
        get_observability().score_current_trace(evaluation)

        return AgentResult(
            agent="RAG Agent",
            answer=answer,
            sources=[f"uploaded://{uploaded_file.name}"],
            data={
                "filename": uploaded_file.name,
                "chunk_count": len(chunks),
                "retrieved_chunk_count": len(selected_chunks),
                "retrieved_chunks": selected_chunks,
                "ragas": evaluation.as_dict(),
            },
        )

    def _answer_s3_report(self, question: str) -> AgentResult | None:
        if not self.settings.reports_bucket:
            return None

        ticker = detect_report_ticker(question)
        if not ticker:
            return None

        key = f"financial-reports/{ticker}/5-year/{ticker}-5-year-financial-report.md"
        try:
            s3 = boto3.client("s3", region_name=self.settings.aws_region)
            response = s3.get_object(Bucket=self.settings.reports_bucket, Key=key)
            document_text = response["Body"].read().decode("utf-8", errors="ignore")
        except Exception as exc:
            return AgentResult(
                agent="RAG Agent",
                answer=(
                    f"I found the ticker {ticker}, but could not read its S3 report yet. "
                    f"Please verify the report exists at s3://{self.settings.reports_bucket}/{key}. "
                    f"Error: {exc}"
                ),
                sources=[f"s3://{self.settings.reports_bucket}/{key}"],
                data={"ticker": ticker, "s3_key": key, "s3_error": str(exc)},
            )

        chunks = chunk_text(document_text)
        selected_chunks = retrieve_relevant_chunks(question, chunks)
        answer = build_grounded_report_answer(
            question,
            f"s3://{self.settings.reports_bucket}/{key}",
            selected_chunks,
        )
        evaluation = get_ragas_evaluator().evaluate(
            question=question,
            answer=answer,
            contexts=selected_chunks,
        )
        get_observability().score_current_trace(evaluation)
        return AgentResult(
            agent="RAG Agent",
            answer=answer,
            sources=[f"s3://{self.settings.reports_bucket}/{key}"],
            data={
                "ticker": ticker,
                "s3_key": key,
                "chunk_count": len(chunks),
                "retrieved_chunk_count": len(selected_chunks),
                "retrieved_chunks": selected_chunks,
                "opensearch_status": "OpenSearch unavailable; answered from S3 report fallback.",
                "ragas": evaluation.as_dict(),
            },
        )


def extract_uploaded_file_text(uploaded_file: Any) -> str:
    file_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()
    file_type = (getattr(uploaded_file, "type", "") or "").lower()

    if filename.endswith(".pdf") or "pdf" in file_type:
        reader = PdfReader(io.BytesIO(file_bytes))
        page_text: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                page_text.append(f"[Page {page_number}]\n{text}")
        return "\n\n".join(page_text)

    return file_bytes.decode("utf-8", errors="ignore")


def detect_report_ticker(question: str) -> str | None:
    aliases = {
        "AAPL": ["aapl", "apple"],
        "MSFT": ["msft", "microsoft"],
        "NVDA": ["nvda", "nvidia", "nvdia"],
        "META": ["meta", "facebook"],
        "AMZN": ["amzn", "amazon"],
        "GOOGL": ["googl", "google", "alphabet"],
        "AVGO": ["avgo", "broadcom"],
        "TSLA": ["tsla", "tesla"],
        "COST": ["cost", "costco"],
        "NFLX": ["nflx", "netflix"],
    }
    normalized = question.lower()
    for ticker, names in aliases.items():
        if any(re.search(rf"\b{re.escape(name)}\b", normalized) for name in names):
            return ticker
    return None


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def question_terms(question: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "about",
        "above",
        "for",
        "from",
        "give",
        "in",
        "is",
        "me",
        "of",
        "on",
        "please",
        "report",
        "stock",
        "summary",
        "the",
        "this",
        "to",
        "with",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9%.-]+", question)
        if token.lower() not in stop_words and len(token) > 2
    }


def retrieve_relevant_chunks(question: str, chunks: list[str], top_k: int = 5) -> list[str]:
    terms = question_terms(question)
    if not terms:
        return chunks[:top_k]

    scored_chunks = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(chunk_lower.count(term) for term in terms)
        if any(keyword in chunk_lower for keyword in ["revenue", "income", "cash", "debt", "margin"]):
            score += 1
        scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for score, chunk in scored_chunks[:top_k] if score > 0]
    return selected or chunks[:top_k]


def extract_key_financial_lines(chunks: list[str], limit: int = 12) -> list[str]:
    important_patterns = [
        "revenue",
        "net income",
        "operating income",
        "cash flow",
        "free cash flow",
        "debt",
        "assets",
        "liabilities",
        "gross margin",
        "operating margin",
        "eps",
        "earnings",
    ]
    lines: list[str] = []
    for chunk in chunks:
        sentences = re.split(r"(?<=[.!?])\s+", chunk)
        for sentence in sentences:
            sentence_clean = sentence.strip()
            if any(pattern in sentence_clean.lower() for pattern in important_patterns):
                lines.append(sentence_clean[:350])
            if len(lines) >= limit:
                return lines
    return lines


def build_grounded_report_answer(question: str, filename: str, chunks: list[str]) -> str:
    key_lines = extract_key_financial_lines(chunks)
    context_preview = "\n".join(f"- {line}" for line in key_lines[:10])
    if not context_preview:
        context_preview = "\n".join(f"- {chunk[:300]}..." for chunk in chunks[:3])

    return "\n".join(
        [
            "Uploaded financial report analysis",
            "",
            f"File: {filename}",
            f"Question: {question}",
            "",
            "Relevant findings from the uploaded document:",
            context_preview,
            "",
            "Summary:",
            (
                "The RAG Agent extracted text from the uploaded document, split it into "
                "overlapping chunks, selected the chunks most relevant to your question, "
                "and summarized only from that uploaded content."
            ),
            "",
            "Important note:",
            (
                "This is a grounded document summary, not financial advice. "
                "Please verify the original report before making investment decisions."
            ),
        ]
    )
