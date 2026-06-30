"""Stock Market Agent tools for a shared MCP server.

Copy this file into your common MCP server project, or import these tool
functions from your existing MCP server.

Tools exposed:

- stock_research
- financial_report_research
- user_context
- portfolio_analysis
- investment_research

Install dependencies in the MCP server environment:

    pip install mcp yfinance pandas

Run standalone for local testing:

    python common_mcp_stock_market_tools.py

Important:
This is educational stock research only. It must not be treated as regulated
financial advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yfinance as yf
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("stock-market-shared-tools")


# ---------------------------------------------------------------------------
# Demo user and portfolio storage
# ---------------------------------------------------------------------------
# Replace these dictionaries with your real database calls later.

DEMO_USERS: dict[str, dict[str, Any]] = {
    "demo-user": {
        "user_id": "demo-user",
        "risk_profile": "balanced",
        "investment_goal": "long-term growth",
        "watchlist": ["AAPL", "MSFT", "NVDA", "META"],
    }
}

DEMO_PORTFOLIOS: dict[str, list[dict[str, Any]]] = {
    "demo-user": [
        {"ticker": "AAPL", "quantity": 10, "average_buy_price": 180.0},
        {"ticker": "MSFT", "quantity": 6, "average_buy_price": 330.0},
        {"ticker": "NVDA", "quantity": 8, "average_buy_price": 120.0},
    ]
}


COMPANY_NAME_TO_TICKER = {
    "apple": "AAPL",
    "apple inc": "AAPL",
    "microsoft": "MSFT",
    "microsoft corporation": "MSFT",
    "amazon": "AMZN",
    "amazon.com": "AMZN",
    "meta": "META",
    "meta platforms": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "nvdia": "NVDA",
    "tesla": "TSLA",
    "netflix": "NFLX",
    "costco": "COST",
    "costco wholesale": "COST",
    "broadcom": "AVGO",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "cisco": "CSCO",
    "cisco systems": "CSCO",
    "csx": "CSX",
    "csx corporation": "CSX",
    "pepsico": "PEP",
    "pepsi": "PEP",
    "target": "TGT",
    "target corporation": "TGT",
    "marvell": "MRVL",
    "marvell technology": "MRVL",
}


@dataclass
class Quote:
    ticker: str
    company_name: str | None
    price: float | None
    previous_close: float | None
    currency: str | None
    market_cap: int | None
    sector: str | None
    industry: str | None


def _extract_tickers_or_company_names(text: str) -> list[str]:
    """Extract tickers from a user question.

    This deliberately avoids returning a default top-10 list. If the user asks
    about one company, return one ticker. If the user asks for comparison,
    return only the mentioned tickers.
    """

    normalized = text.lower()
    found: list[str] = []

    # Match known company names first.
    for company_name, ticker in COMPANY_NAME_TO_TICKER.items():
        if re.search(rf"\b{re.escape(company_name)}\b", normalized):
            found.append(ticker)

    # Match uppercase ticker-like tokens from original text.
    for token in re.findall(r"\b[A-Z]{1,5}\b", text):
        if token not in {"USA", "PDF", "RAG", "MCP", "AWS"}:
            found.append(token)

    # Preserve order and remove duplicates.
    unique: list[str] = []
    for ticker in found:
        if ticker not in unique:
            unique.append(ticker)

    return unique


def _get_quote(ticker: str) -> Quote:
    stock = yf.Ticker(ticker)
    info = stock.get_info()

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

    return Quote(
        ticker=ticker.upper(),
        company_name=info.get("longName") or info.get("shortName"),
        price=float(price) if price is not None else None,
        previous_close=float(previous_close) if previous_close is not None else None,
        currency=info.get("currency"),
        market_cap=info.get("marketCap"),
        sector=info.get("sector"),
        industry=info.get("industry"),
    )


def _format_money(value: float | int | None, currency: str | None = "USD") -> str:
    if value is None:
        return "not available"
    if abs(value) >= 1_000_000_000_000:
        return f"{currency} {value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"{currency} {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{currency} {value / 1_000_000:.2f}M"
    return f"{currency} {value:,.2f}"


def _price_change_percent(price: float | None, previous_close: float | None) -> float | None:
    if price is None or previous_close in (None, 0):
        return None
    return ((price - previous_close) / previous_close) * 100


def _risk_alerts_for_portfolio(
    holdings: list[dict[str, Any]],
    quotes: dict[str, Quote],
    max_single_position_percent: float = 35.0,
) -> list[str]:
    values: dict[str, float] = {}
    for holding in holdings:
        ticker = str(holding["ticker"]).upper()
        quote = quotes.get(ticker)
        price = quote.price if quote else None
        values[ticker] = float(holding["quantity"]) * float(price or 0)

    total_value = sum(values.values())
    if total_value <= 0:
        return ["Portfolio value cannot be calculated because prices are unavailable."]

    alerts: list[str] = []
    for ticker, value in values.items():
        weight = (value / total_value) * 100
        if weight > max_single_position_percent:
            alerts.append(
                f"{ticker} is {weight:.1f}% of the portfolio, above the "
                f"{max_single_position_percent:.1f}% concentration limit."
            )

    if not alerts:
        alerts.append("No major single-stock concentration alert found.")

    return alerts


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
def stock_research(question: str) -> dict[str, Any]:
    """Answer stock price, stock detail, and comparison questions."""

    tickers = _extract_tickers_or_company_names(question)
    if not tickers:
        return {
            "answer": (
                "Please provide a company name or ticker, for example "
                "`Apple stock price`, `Cisco Systems share price`, or "
                "`compare Apple and Meta`."
            ),
            "sources": [],
            "tickers": [],
        }

    quotes = [_get_quote(ticker) for ticker in tickers]

    lines: list[str] = []
    for quote in quotes:
        change_percent = _price_change_percent(quote.price, quote.previous_close)
        change_text = (
            f"{change_percent:+.2f}% vs previous close"
            if change_percent is not None
            else "change not available"
        )

        lines.append(
            "\n".join(
                [
                    f"{quote.ticker} — {quote.company_name or 'Company name unavailable'}",
                    f"- Price: {_format_money(quote.price, quote.currency or 'USD')}",
                    f"- Previous close: {_format_money(quote.previous_close, quote.currency or 'USD')}",
                    f"- Daily change: {change_text}",
                    f"- Market cap: {_format_money(quote.market_cap, quote.currency or 'USD')}",
                    f"- Sector: {quote.sector or 'not available'}",
                    f"- Industry: {quote.industry or 'not available'}",
                ]
            )
        )

    if len(quotes) > 1:
        answer = "Stock comparison:\n\n" + "\n\n".join(lines)
    else:
        answer = "Stock details:\n\n" + lines[0]

    return {
        "answer": answer,
        "sources": ["Yahoo Finance via yfinance"],
        "tickers": [quote.ticker for quote in quotes],
        "quotes": [quote.__dict__ for quote in quotes],
    }


@mcp.tool()
def financial_report_research(
    question: str,
    uploaded_filename: str | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    """Analyze uploaded or stored financial reports.

    Replace the placeholder section with your real S3/OpenSearch/Bedrock RAG
    implementation when the shared MCP server is connected to AWS.
    """

    tickers = [ticker.upper()] if ticker else _extract_tickers_or_company_names(question)

    if uploaded_filename:
        answer = (
            f"Uploaded document `{uploaded_filename}` was selected for RAG analysis. "
            "Connect this MCP tool to your document extraction, chunking, embeddings, "
            "OpenSearch retrieval, and Bedrock summary flow to return the real analysis."
        )
        sources = [f"uploaded://{uploaded_filename}"]
    elif tickers:
        answer = (
            f"Financial report research requested for {', '.join(tickers)}. "
            "Connect this tool to S3 financial reports, OpenSearch vector search, "
            "and Bedrock to return grounded report analysis."
        )
        sources = [f"s3://financial-reports/{ticker}/" for ticker in tickers]
    else:
        answer = (
            "Please provide a ticker/company or upload a financial report for RAG analysis."
        )
        sources = []

    return {
        "answer": answer,
        "sources": sources,
        "tickers": tickers,
    }


@mcp.tool()
def user_context(user_id: str, question: str) -> dict[str, Any]:
    """Return user profile, watchlist, and risk preference."""

    user = DEMO_USERS.get(user_id)
    if not user:
        return {
            "answer": f"No user profile found for `{user_id}`.",
            "user_id": user_id,
            "watchlist": [],
        }

    if "watchlist" in question.lower():
        answer = f"Your watchlist contains: {', '.join(user['watchlist'])}."
    elif "risk" in question.lower():
        answer = f"Your current risk profile is `{user['risk_profile']}`."
    else:
        answer = (
            f"User `{user_id}` has a `{user['risk_profile']}` risk profile and "
            f"investment goal: {user['investment_goal']}."
        )

    return {
        "answer": answer,
        **user,
    }


@mcp.tool()
def portfolio_analysis(user_id: str, question: str) -> dict[str, Any]:
    """Analyze user portfolio value, allocation, gain/loss, and risk alerts."""

    holdings = DEMO_PORTFOLIOS.get(user_id, [])
    if not holdings:
        return {
            "answer": f"No portfolio holdings found for `{user_id}`.",
            "total_value": 0,
            "risk_alerts": [],
        }

    tickers = [str(holding["ticker"]).upper() for holding in holdings]
    quotes = {ticker: _get_quote(ticker) for ticker in tickers}

    rows: list[dict[str, Any]] = []
    total_value = 0.0
    total_cost = 0.0

    for holding in holdings:
        ticker = str(holding["ticker"]).upper()
        quantity = float(holding["quantity"])
        average_buy_price = float(holding["average_buy_price"])
        quote = quotes[ticker]
        current_price = float(quote.price or 0)
        market_value = quantity * current_price
        cost_value = quantity * average_buy_price
        gain_loss = market_value - cost_value

        total_value += market_value
        total_cost += cost_value

        rows.append(
            {
                "ticker": ticker,
                "quantity": quantity,
                "average_buy_price": average_buy_price,
                "current_price": current_price,
                "market_value": market_value,
                "gain_loss": gain_loss,
            }
        )

    alerts = _risk_alerts_for_portfolio(holdings, quotes)
    total_gain_loss = total_value - total_cost
    total_gain_loss_percent = (total_gain_loss / total_cost * 100) if total_cost else 0

    allocation_lines = []
    for row in rows:
        weight = (row["market_value"] / total_value * 100) if total_value else 0
        allocation_lines.append(
            f"- {row['ticker']}: {weight:.1f}% allocation, "
            f"value {_format_money(row['market_value'])}, "
            f"gain/loss {_format_money(row['gain_loss'])}"
        )

    answer = "\n".join(
        [
            "Portfolio analysis:",
            f"- Total value: {_format_money(total_value)}",
            f"- Total gain/loss: {_format_money(total_gain_loss)} ({total_gain_loss_percent:+.2f}%)",
            "",
            "Allocation:",
            *allocation_lines,
            "",
            "Risk alerts:",
            *[f"- {alert}" for alert in alerts],
        ]
    )

    return {
        "answer": answer,
        "total_value": total_value,
        "total_gain_loss": total_gain_loss,
        "total_gain_loss_percent": total_gain_loss_percent,
        "holdings": rows,
        "risk_alerts": alerts,
        "sources": ["Yahoo Finance via yfinance", "Demo portfolio storage"],
    }


@mcp.tool()
def investment_research(user_id: str, question: str) -> dict[str, Any]:
    """Generate educational investment research using user, stock, and portfolio context."""

    tickers = _extract_tickers_or_company_names(question)
    if not tickers:
        return {
            "answer": (
                "Please provide a company name or ticker for investment research, "
                "for example `Should I buy PepsiCo?`."
            ),
            "sources": [],
            "disclaimer": "Educational research only, not financial advice.",
        }

    user = DEMO_USERS.get(user_id, DEMO_USERS["demo-user"])
    stock_result = stock_research(question)
    portfolio_result = portfolio_analysis(user_id, "analyze my portfolio")

    answer = "\n\n".join(
        [
            "Investment research summary:",
            f"User risk profile: {user['risk_profile']}",
            stock_result["answer"],
            "Portfolio context:",
            portfolio_result["answer"],
            "Interpretation:",
            (
                "This stock may be worth further research if it fits your risk profile, "
                "portfolio allocation, and investment time horizon. Review valuation, "
                "earnings trend, debt, cash flow, and sector risk before making a decision."
            ),
            (
                "Disclaimer: This is educational research only. It is not financial, "
                "legal, or tax advice. Consider speaking with a licensed financial advisor."
            ),
        ]
    )

    return {
        "answer": answer,
        "tickers": tickers,
        "sources": list(
            dict.fromkeys(
                stock_result.get("sources", []) + portfolio_result.get("sources", [])
            )
        ),
        "disclaimer": "Educational research only, not financial advice.",
    }


if __name__ == "__main__":
    mcp.run()
