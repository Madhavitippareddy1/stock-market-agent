from __future__ import annotations

import re
from typing import Any

import yfinance as yf

from stock_market_agent.models import AgentResult
from stock_market_agent.services.mcp_client import McpClient


COMPANY_NAME_TO_TICKER = {
    "apple": "AAPL",
    "apple inc": "AAPL",
    "amazon": "AMZN",
    "amazon.com": "AMZN",
    "amazon com": "AMZN",
    "microsoft": "MSFT",
    "meta": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "nvdia": "NVDA",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "tesla": "TSLA",
    "broadcom": "AVGO",
    "costco": "COST",
    "netflix": "NFLX",
    "walmart": "WMT",
    "walmart inc": "WMT",
    "target": "TGT",
    "target corporation": "TGT",
    "pepsico": "PEP",
    "pepsi": "PEP",
    "cisco": "CSCO",
    "cisco systems": "CSCO",
    "csx": "CSX",
    "csx corporation": "CSX",
}


def _is_mcp_error(result: dict[str, Any]) -> bool:
    answer = str(result.get("answer", "")).lower()
    return "mcp tool" in answer and any(
        marker in answer
        for marker in ["unavailable", "timed out", "not configured", "returned no content"]
    )


def _extract_requested_tickers(question: str) -> list[str]:
    normalized = question.lower()
    matched: list[tuple[int, str]] = []

    for company_name, ticker in sorted(
        COMPANY_NAME_TO_TICKER.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        match = re.search(rf"\b{re.escape(company_name)}\b", normalized)
        if match:
            matched.append((match.start(), ticker))

    ignored_tokens = {
        "A",
        "I",
        "AM",
        "IS",
        "IT",
        "THE",
        "USA",
        "PDF",
        "RAG",
        "MCP",
        "AWS",
        "API",
    }
    for token in re.findall(r"\b[A-Z]{1,5}\b", question):
        if token not in ignored_tokens:
            token_match = re.search(rf"\b{re.escape(token)}\b", question)
            matched.append((token_match.start() if token_match else 0, token))

    unique: list[str] = []
    for _, ticker in sorted(matched, key=lambda item: item[0]):
        if ticker not in unique:
            unique.append(ticker)
    return unique


def _money(value: float | int | None, currency: str = "USD") -> str:
    if value is None:
        return "not available"
    if abs(value) >= 1_000_000_000_000:
        return f"{currency} {value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"{currency} {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{currency} {value / 1_000_000:.2f}M"
    return f"{currency} {value:,.2f}"


def _quote_from_yfinance(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    info: dict[str, Any] = {}
    try:
        info = stock.get_info() or {}
    except Exception:
        info = {}

    fast_info = {}
    try:
        fast_info = dict(stock.fast_info or {})
    except Exception:
        fast_info = {}

    price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or fast_info.get("last_price")
        or fast_info.get("lastPrice")
    )
    previous_close = (
        info.get("previousClose")
        or info.get("regularMarketPreviousClose")
        or fast_info.get("previous_close")
        or fast_info.get("previousClose")
    )
    currency = info.get("currency") or fast_info.get("currency") or "USD"

    return {
        "ticker": ticker.upper(),
        "company_name": info.get("longName") or info.get("shortName"),
        "price": float(price) if price is not None else None,
        "previous_close": float(previous_close) if previous_close is not None else None,
        "currency": currency,
        "market_cap": info.get("marketCap") or fast_info.get("market_cap"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }


def _direct_stock_fallback(question: str, mcp_error: str) -> dict[str, Any]:
    tickers = _extract_requested_tickers(question)
    if not tickers:
        return {
            "answer": (
                "The shared MCP stock tool is currently unavailable, and I could not "
                "identify a ticker/company from the question. Please try a ticker like "
                "`AAPL` or a company name like `Apple`."
            ),
            "sources": ["MCP fallback"],
            "mcp_error": mcp_error,
        }

    quotes = [_quote_from_yfinance(ticker) for ticker in tickers]
    sections: list[str] = []
    for quote in quotes:
        price = quote.get("price")
        previous_close = quote.get("previous_close")
        change_text = "not available"
        if price is not None and previous_close not in (None, 0):
            change = ((price - previous_close) / previous_close) * 100
            change_text = f"{change:+.2f}% vs previous close"

        currency = quote.get("currency") or "USD"
        sections.append(
            "\n".join(
                [
                    f"{quote['ticker']} — {quote.get('company_name') or 'Company name unavailable'}",
                    f"- Price: {_money(price, currency)}",
                    f"- Previous close: {_money(previous_close, currency)}",
                    f"- Daily change: {change_text}",
                    f"- Market cap: {_money(quote.get('market_cap'), currency)}",
                    f"- Sector: {quote.get('sector') or 'not available'}",
                    f"- Industry: {quote.get('industry') or 'not available'}",
                ]
            )
        )

    prefix = (
        "Stock comparison from direct fallback data:"
        if len(quotes) > 1
        else "Stock details from direct fallback data:"
    )
    return {
        "answer": (
            f"{prefix}\n\n"
            + "\n\n".join(sections)
            + "\n\nNote: The shared MCP server stock tool is unavailable right now, "
            "so this response used direct Yahoo Finance fallback data. Educational "
            "research only, not financial advice."
        ),
        "sources": ["Yahoo Finance via yfinance fallback"],
        "tickers": [quote["ticker"] for quote in quotes],
        "quotes": quotes,
        "mcp_error": mcp_error,
    }


class StockAgent:
    def __init__(self, mcp_client: McpClient) -> None:
        self.mcp_client = mcp_client

    def answer(self, question: str) -> AgentResult:
        normalized = question.lower()
        if any(
            phrase in normalized
            for phrase in ["best stock", "suggest", "recommend", "top stock", "this month"]
        ):
            result = self.mcp_client.call_tool(
                "suggest_best_stock_of_month",
                {"question": question},
            )
        elif any(
            phrase in normalized
            for phrase in [
                "5 year",
                "5-year",
                "five year",
                "five-year",
                "3 year",
                "3-year",
                "three year",
                "three-year",
                "previous",
                "monthly",
                "month analysis",
                "performance",
                "profit",
                "loss",
                "analyse",
                "analyze",
                "analysis",
            ]
        ):
            result = self.mcp_client.call_tool(
                "stock_performance_analysis",
                {"question": question},
            )
        else:
            result = self.mcp_client.call_tool("stock_research", {"question": question})

        if _is_mcp_error(result):
            result = _direct_stock_fallback(question, result.get("answer", "MCP tool failed."))

        answer = result.get("answer") or "Stock research tool did not return an answer yet."
        return AgentResult(
            agent="Stock Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )
