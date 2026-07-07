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

BUDGET_SCREEN_TICKERS = ["CSCO", "PFE", "KO", "T", "VZ", "INTC", "WBD", "CMCSA", "PYPL", "SBUX"]
GBP_TO_USD_ESTIMATE = 1.27


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


def _is_five_year_question(question: str) -> bool:
    normalized = question.lower()
    return any(
        phrase in normalized
        for phrase in ["5 year", "5-year", "five year", "five-year", "5 years", "five years"]
    )


def _format_percent(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:+.2f}%"


def _extract_budget(question: str) -> dict[str, Any] | None:
    currency = None
    amount = None
    symbol_match = re.search(r"([£$])\s*([0-9]+(?:\.[0-9]+)?)", question)
    if symbol_match:
        currency = "GBP" if symbol_match.group(1) == "£" else "USD"
        amount = float(symbol_match.group(2))
    else:
        word_match = re.search(
            r"\b([0-9]+(?:\.[0-9]+)?)\s*(pounds?|gbp|dollars?|usd)\b",
            question,
            flags=re.IGNORECASE,
        )
        if word_match:
            amount = float(word_match.group(1))
            word = word_match.group(2).lower()
            currency = "GBP" if word in {"pound", "pounds", "gbp"} else "USD"

    if amount is None or currency is None:
        return None
    budget_usd = amount * GBP_TO_USD_ESTIMATE if currency == "GBP" else amount
    return {
        "amount": amount,
        "currency": currency,
        "budget_usd": budget_usd,
        "display": f"{currency} {amount:,.2f}",
    }


def _budget_stock_screen(question: str) -> dict[str, Any] | None:
    budget = _extract_budget(question)
    if not budget:
        return None

    quotes = [_quote_from_yfinance(ticker) for ticker in BUDGET_SCREEN_TICKERS]
    valid_quotes = [quote for quote in quotes if quote.get("price") is not None]
    if not valid_quotes:
        return None

    affordable = [
        quote
        for quote in valid_quotes
        if (quote.get("currency") or "USD") == "USD"
        and float(quote.get("price") or 0) <= float(budget["budget_usd"])
    ]
    candidates = affordable or sorted(valid_quotes, key=lambda quote: float(quote.get("price") or 999999))[:5]

    def score_quote(quote: dict[str, Any]) -> float:
        price = float(quote.get("price") or 0)
        previous_close = float(quote.get("previous_close") or price or 1)
        market_cap = float(quote.get("market_cap") or 0)
        daily_change = ((price - previous_close) / previous_close) * 100 if previous_close else 0
        budget_fit = 20 if price <= float(budget["budget_usd"]) else -20
        size_score = min(market_cap / 1_000_000_000_000, 1.0) * 20
        momentum_score = max(min(daily_change, 5), -5)
        return budget_fit + size_score + momentum_score

    ranked = sorted(candidates, key=score_quote, reverse=True)[:5]
    top = ranked[0]
    rows: list[str] = []
    for quote in ranked:
        price = float(quote.get("price") or 0)
        previous_close = float(quote.get("previous_close") or price or 1)
        daily_change = ((price - previous_close) / previous_close) * 100 if previous_close else 0
        affordable_text = (
            "fits budget"
            if price <= float(budget["budget_usd"])
            else "above budget; fractional shares required"
        )
        rows.append(
            "- "
            f"{quote['ticker']} - {quote.get('company_name') or 'Company name unavailable'}: "
            f"{_money(price, quote.get('currency') or 'USD')}, "
            f"{daily_change:+.2f}% vs previous close, "
            f"{quote.get('sector') or 'sector unavailable'}; {affordable_text}."
        )

    answer = "\n\n".join(
        [
            "Budget-aware investment screen",
            f"Budget detected: {budget['display']} (about USD {budget['budget_usd']:,.2f} using an estimated FX rate).",
            f"Short answer: {top['ticker']} is the strongest fit from this simple budget screen, but compare the full shortlist below before deciding.",
            "Shortlisted stocks:",
            "\n".join(rows),
            "Why not default to expensive stocks:",
            "- A stock above your budget only works if your broker supports fractional shares. Otherwise, it is not directly buyable with this budget.",
            "What to verify next:",
            "- Latest earnings, valuation, revenue growth, debt, dividend policy, recent news, and whether your broker supports fractional shares.",
            "Disclaimer: Educational research only, not financial advice. Please consult a licensed financial advisor before investing.",
        ]
    )
    return {
        "answer": answer,
        "sources": ["Yahoo Finance via yfinance budget screen"],
        "tickers": [quote["ticker"] for quote in ranked],
        "quotes": ranked,
        "budget": budget,
        "budget_screen": True,
    }


def _five_year_stock_report(question: str) -> dict[str, Any] | None:
    tickers = _extract_requested_tickers(question)
    if not tickers:
        return None

    sections: list[str] = []
    history_by_ticker: dict[str, list[dict[str, Any]]] = {}
    quote_rows: list[dict[str, Any]] = []

    for ticker in tickers:
        quote = _quote_from_yfinance(ticker)
        quote_rows.append(quote)
        currency = quote.get("currency") or "USD"
        stock = yf.Ticker(ticker)
        try:
            history = stock.history(period="5y", interval="1mo", auto_adjust=False)
        except Exception:
            history = None

        if history is None or history.empty or "Close" not in history:
            sections.append(
                "\n".join(
                    [
                        f"{ticker} - {quote.get('company_name') or 'Company name unavailable'}",
                        f"- Current price: {_money(quote.get('price'), currency)}",
                        "- 5-year monthly history is not available right now.",
                    ]
                )
            )
            history_by_ticker[ticker] = []
            continue

        clean_history = history.dropna(subset=["Close"]).copy()
        monthly_rows: list[dict[str, Any]] = []
        for date_index, row in clean_history.iterrows():
            monthly_rows.append(
                {
                    "month": date_index.strftime("%Y-%m"),
                    "open": round(float(row.get("Open", 0) or 0), 2),
                    "high": round(float(row.get("High", 0) or 0), 2),
                    "low": round(float(row.get("Low", 0) or 0), 2),
                    "close": round(float(row.get("Close", 0) or 0), 2),
                    "volume": int(row.get("Volume", 0) or 0),
                }
            )
        history_by_ticker[ticker] = monthly_rows

        first_close = float(clean_history["Close"].iloc[0])
        last_close = float(clean_history["Close"].iloc[-1])
        total_return = ((last_close - first_close) / first_close) * 100 if first_close else None
        high_close = float(clean_history["Close"].max())
        low_close = float(clean_history["Close"].min())

        yearly = clean_history["Close"].resample("YE").last().tail(5)
        yearly_lines = [
            f"  - {date_index.year}: {_money(float(close), currency)}"
            for date_index, close in yearly.items()
        ]

        monthly_returns = clean_history["Close"].pct_change().dropna() * 100
        best_month = None
        worst_month = None
        if not monthly_returns.empty:
            best_idx = monthly_returns.idxmax()
            worst_idx = monthly_returns.idxmin()
            best_month = f"{best_idx.strftime('%Y-%m')} ({monthly_returns.loc[best_idx]:+.2f}%)"
            worst_month = f"{worst_idx.strftime('%Y-%m')} ({monthly_returns.loc[worst_idx]:+.2f}%)"

        sections.append(
            "\n".join(
                [
                    f"{ticker} - {quote.get('company_name') or 'Company name unavailable'}",
                    f"- Current price: {_money(quote.get('price'), currency)}",
                    f"- 5-year start close: {_money(first_close, currency)}",
                    f"- Latest monthly close: {_money(last_close, currency)}",
                    f"- 5-year return: {_format_percent(total_return)}",
                    f"- Highest monthly close: {_money(high_close, currency)}",
                    f"- Lowest monthly close: {_money(low_close, currency)}",
                    f"- Best month: {best_month or 'not available'}",
                    f"- Worst month: {worst_month or 'not available'}",
                    "- Year-end close snapshot:",
                    *yearly_lines,
                ]
            )
        )

    return {
        "answer": (
            "5-year stock report\n\n"
            + "\n\n".join(sections)
            + "\n\nThe chart below shows monthly close prices. Educational research only, not financial advice."
        ),
        "sources": ["Yahoo Finance via yfinance"],
        "tickers": [quote["ticker"] for quote in quote_rows],
        "quotes": quote_rows,
        "history": history_by_ticker,
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
                    f"{quote['ticker']} - {quote.get('company_name') or 'Company name unavailable'}",
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
        requested_tickers = _extract_requested_tickers(question)
        normalized = question.lower()
        if _is_five_year_question(question):
            result = _five_year_stock_report(question)
            if result is None:
                result = self.mcp_client.call_tool(
                    "stock_performance_analysis",
                    {"question": question},
                )
        elif any(
            phrase in normalized
            for phrase in ["best stock", "suggest", "recommend", "top stock", "this month"]
        ):
            result = _budget_stock_screen(question) or self.mcp_client.call_tool(
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

        returned_tickers = [str(ticker).upper() for ticker in result.get("tickers", [])]
        answer_text = str(result.get("answer", ""))
        missing_requested_ticker = bool(requested_tickers) and not all(
            ticker in returned_tickers or ticker in answer_text.upper()
            for ticker in requested_tickers
        )
        if _is_mcp_error(result) or missing_requested_ticker:
            result = _direct_stock_fallback(question, result.get("answer", "MCP tool failed."))

        answer = result.get("answer") or "Stock research tool did not return an answer yet."
        return AgentResult(
            agent="Stock Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )
