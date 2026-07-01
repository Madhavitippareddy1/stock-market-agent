from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yfinance as yf


DEMO_USER = {
    "user_id": "demo-user",
    "display_name": "Demo User",
    "sector": "technology",
    "risk_profile": "balanced",
    "investment_goal": "long-term growth",
    "watchlist": ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"],
}

DEMO_PORTFOLIO = [
    {"ticker": "AAPL", "quantity": 10, "average_buy_price": 180.0},
    {"ticker": "MSFT", "quantity": 6, "average_buy_price": 330.0},
    {"ticker": "NVDA", "quantity": 8, "average_buy_price": 120.0},
    {"ticker": "META", "quantity": 5, "average_buy_price": 410.0},
    {"ticker": "AMZN", "quantity": 7, "average_buy_price": 170.0},
    {"ticker": "GOOGL", "quantity": 6, "average_buy_price": 160.0},
    {"ticker": "AVGO", "quantity": 4, "average_buy_price": 260.0},
    {"ticker": "TSLA", "quantity": 5, "average_buy_price": 250.0},
    {"ticker": "COST", "quantity": 3, "average_buy_price": 700.0},
    {"ticker": "NFLX", "quantity": 8, "average_buy_price": 500.0},
]

SECTOR_USER_BLUEPRINTS = [
    ("technology", "aggressive", "AI, cloud, semiconductors, and software growth", ["AAPL", "MSFT", "NVDA", "AVGO"]),
    ("consumer defensive", "balanced", "stable retail, groceries, and essential consumer demand", ["WMT", "COST", "PEP", "PG"]),
    ("healthcare", "balanced", "large-cap healthcare, devices, and pharmaceutical exposure", ["UNH", "JNJ", "LLY", "MRK"]),
    ("financial services", "balanced", "banks, payment networks, and diversified financials", ["JPM", "BAC", "V", "MA"]),
    ("energy", "moderate", "oil, gas, and energy cash-flow opportunities", ["XOM", "CVX", "COP", "SLB"]),
    ("communication services", "aggressive", "digital advertising, streaming, and connectivity growth", ["GOOGL", "META", "NFLX", "TMUS"]),
    ("consumer cyclical", "aggressive", "e-commerce, autos, travel, and discretionary spending", ["AMZN", "TSLA", "HD", "MCD"]),
    ("industrials", "balanced", "transport, aerospace, machinery, and infrastructure", ["CAT", "BA", "UPS", "CSX"]),
    ("utilities", "conservative", "dividend-focused regulated utilities and stable cash flow", ["NEE", "DUK", "SO", "AEP"]),
    ("real estate", "moderate", "REIT income and property-sector diversification", ["PLD", "AMT", "EQIX", "O"]),
]

DIVERSIFIED_STOCK_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AVGO", "WMT", "COST", "PEP", "PG", "UNH", "JNJ",
    "LLY", "MRK", "JPM", "BAC", "V", "MA", "XOM", "CVX", "COP", "SLB",
    "GOOGL", "META", "NFLX", "TMUS", "AMZN", "TSLA", "HD", "MCD", "CAT", "BA",
    "UPS", "CSX", "NEE", "DUK", "SO", "AEP", "PLD", "AMT", "EQIX", "O",
]

SEED_DISPLAY_NAMES = [
    "Aarav Patel", "Sophia Johnson", "Liam Smith", "Maya Rodriguez", "Noah Williams",
    "Emma Brown", "Ethan Davis", "Olivia Wilson", "Lucas Martinez", "Ava Anderson",
    "Mason Thomas", "Isabella Taylor", "Logan Moore", "Mia Jackson", "James Martin",
    "Charlotte Lee", "Benjamin Harris", "Amelia Clark", "Henry Lewis", "Harper Walker",
    "Alexander Hall", "Evelyn Allen", "Daniel Young", "Abigail King", "Michael Wright",
    "Emily Scott", "Sebastian Green", "Elizabeth Adams", "Jack Baker", "Sofia Gonzalez",
    "William Nelson", "Grace Carter", "David Mitchell", "Chloe Perez", "Joseph Roberts",
    "Victoria Turner", "Samuel Phillips", "Aria Campbell", "Matthew Parker", "Ella Evans",
    "John Edwards", "Layla Collins", "Anthony Stewart", "Scarlett Sanchez",
    "Christopher Morris", "Zoey Rogers", "Andrew Reed", "Nora Cook", "Joshua Morgan",
    "Lily Bell",
]


@dataclass
class LocalQuote:
    ticker: str
    company_name: str | None
    price: float | None
    previous_close: float | None
    currency: str
    market_cap: int | None
    sector: str | None
    industry: str | None


def build_seed_users() -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    users: dict[str, dict[str, Any]] = {"demo-user": DEMO_USER}
    portfolios: dict[str, list[dict[str, Any]]] = {"demo-user": DEMO_PORTFOLIO}

    for sector_index, (sector, risk_profile, goal, watchlist) in enumerate(SECTOR_USER_BLUEPRINTS, start=1):
        sector_slug = re.sub(r"[^a-z0-9]+", "-", sector.lower()).strip("-")
        for investor_index in range(1, 6):
            user_number = ((sector_index - 1) * 5) + investor_index
            user_id = f"user-{sector_slug}-{investor_index:03d}"
            universe_offset = (user_number - 1) % len(DIVERSIFIED_STOCK_UNIVERSE)
            rotated_universe = (
                DIVERSIFIED_STOCK_UNIVERSE[universe_offset:]
                + DIVERSIFIED_STOCK_UNIVERSE[:universe_offset]
            )
            diversified_watchlist = list(dict.fromkeys([*watchlist, *rotated_universe]))[:10]
            rotated_watchlist = (
                diversified_watchlist[investor_index - 1 :]
                + diversified_watchlist[: investor_index - 1]
            )
            users[user_id] = {
                "user_id": user_id,
                "display_name": SEED_DISPLAY_NAMES[user_number - 1],
                "sector": sector,
                "risk_profile": risk_profile,
                "investment_goal": f"{goal}; profile #{user_number:02d}",
                "watchlist": rotated_watchlist,
            }
            portfolios[user_id] = [
                {
                    "ticker": ticker,
                    "quantity": 4 + investor_index + ticker_index,
                    "average_buy_price": float(80 + (sector_index * 9) + (ticker_index * 17)),
                }
                for ticker_index, ticker in enumerate(rotated_watchlist, start=1)
            ]
    return users, portfolios


SEED_USERS, SEED_PORTFOLIOS = build_seed_users()


def list_investment_users() -> list[dict[str, Any]]:
    return [SEED_USERS[user_id] for user_id in sorted(SEED_USERS) if user_id != "demo-user"]


def get_user_profile(user_id: str) -> dict[str, Any] | None:
    return SEED_USERS.get(user_id)


def get_user_portfolio(user_id: str) -> list[dict[str, Any]]:
    return SEED_PORTFOLIOS.get(user_id, [])


def get_quote(ticker: str) -> LocalQuote:
    stock = yf.Ticker(ticker)
    info: dict[str, Any] = {}
    fast_info: dict[str, Any] = {}
    try:
        info = stock.get_info() or {}
    except Exception:
        info = {}
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
    return LocalQuote(
        ticker=ticker.upper(),
        company_name=info.get("longName") or info.get("shortName"),
        price=float(price) if price is not None else None,
        previous_close=float(previous_close) if previous_close is not None else None,
        currency=info.get("currency") or fast_info.get("currency") or "USD",
        market_cap=info.get("marketCap") or fast_info.get("market_cap"),
        sector=info.get("sector"),
        industry=info.get("industry"),
    )


def money(value: float | int | None, currency: str = "USD") -> str:
    if value is None:
        return "not available"
    if abs(value) >= 1_000_000_000_000:
        return f"{currency} {value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"{currency} {value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{currency} {value / 1_000_000:.2f}M"
    return f"{currency} {value:,.2f}"


def risk_alerts_for_portfolio(
    holdings: list[dict[str, Any]],
    quotes: dict[str, LocalQuote],
    max_single_position_percent: float = 35.0,
) -> list[str]:
    values: dict[str, float] = {}
    costs: dict[str, float] = {}
    sectors: dict[str, float] = {}
    missing_prices: list[str] = []

    for holding in holdings:
        ticker = str(holding["ticker"]).upper()
        quote = quotes.get(ticker)
        price = quote.price if quote else None
        quantity = float(holding["quantity"])
        average_buy_price = float(holding["average_buy_price"])
        if price is None:
            missing_prices.append(ticker)
        market_value = quantity * float(price or 0)
        cost_value = quantity * average_buy_price
        values[ticker] = market_value
        costs[ticker] = cost_value
        sector = quote.sector if quote and quote.sector else "Unknown sector"
        sectors[sector] = sectors.get(sector, 0.0) + market_value

    total_value = sum(values.values())
    total_cost = sum(costs.values())
    if total_value <= 0:
        return ["Portfolio value cannot be calculated because prices are unavailable."]

    alerts: list[str] = []
    if missing_prices:
        alerts.append(
            "Data quality alert: live prices were unavailable for "
            f"{', '.join(missing_prices)}, so risk metrics may be incomplete."
        )

    holding_count = len([value for value in values.values() if value > 0])
    if holding_count < 5:
        alerts.append(
            f"Diversification alert: this portfolio has {holding_count} priced holdings. "
            "Consider reviewing whether it is too concentrated in a small number of stocks."
        )

    for ticker, value in values.items():
        weight = (value / total_value) * 100
        if weight > max_single_position_percent:
            alerts.append(
                f"High concentration alert: {ticker} is {weight:.1f}% of the portfolio, "
                f"above the {max_single_position_percent:.1f}% single-stock guideline."
            )
        elif weight > 25:
            alerts.append(
                f"Moderate concentration alert: {ticker} is {weight:.1f}% of the portfolio. "
                "A large single position can increase volatility."
            )

        cost_value = costs.get(ticker, 0)
        gain_loss_percent = ((value - cost_value) / cost_value * 100) if cost_value else 0
        if gain_loss_percent <= -20:
            alerts.append(
                f"Loss alert: {ticker} is down {gain_loss_percent:.1f}% versus average buy price. "
                "Review whether the investment thesis still holds."
            )
        elif -20 < gain_loss_percent <= -10:
            alerts.append(
                f"Watch alert: {ticker} is down {gain_loss_percent:.1f}% versus average buy price."
            )

    for sector, sector_value in sectors.items():
        sector_weight = (sector_value / total_value) * 100
        if sector_weight > 60:
            alerts.append(
                f"Sector concentration alert: {sector} represents {sector_weight:.1f}% "
                "of portfolio value. Sector-specific news could strongly affect results."
            )

    total_gain_loss_percent = ((total_value - total_cost) / total_cost * 100) if total_cost else 0
    if total_gain_loss_percent <= -10:
        alerts.append(
            f"Portfolio drawdown alert: total unrealized return is {total_gain_loss_percent:.1f}%. "
            "Review allocation, time horizon, and risk tolerance."
        )
    elif 0 <= total_gain_loss_percent < 5:
        alerts.append(
            f"Low cushion note: total unrealized return is {total_gain_loss_percent:.1f}%. "
            "Small market moves could turn the portfolio negative."
        )

    if not alerts:
        alerts.append("No major concentration, sector, or unrealized-loss risk alert found from current data.")

    return alerts


def classify_risk_alert(alert: str) -> dict[str, str]:
    normalized = alert.lower()
    severity = "info"
    if any(keyword in normalized for keyword in ["high concentration", "loss alert", "drawdown"]):
        severity = "high"
    elif any(
        keyword in normalized
        for keyword in [
            "moderate",
            "diversification",
            "sector concentration",
            "data quality",
            "watch alert",
            "low cushion",
        ]
    ):
        severity = "medium"
    elif "no major" in normalized:
        severity = "low"
    return {"severity": severity, "message": alert}


def portfolio_analysis(user_id: str) -> dict[str, Any]:
    holdings = get_user_portfolio(user_id)
    if not holdings:
        return {
            "answer": f"No portfolio holdings found for `{user_id}`.",
            "total_value": 0,
            "risk_alerts": [],
            "risk_alert_details": [],
            "holdings": [],
            "sources": ["Local fallback seed portfolio"],
        }

    tickers = [str(holding["ticker"]).upper() for holding in holdings]
    quotes = {ticker: get_quote(ticker) for ticker in tickers}

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

    alerts = risk_alerts_for_portfolio(holdings, quotes)
    total_gain_loss = total_value - total_cost
    total_gain_loss_percent = (total_gain_loss / total_cost * 100) if total_cost else 0
    allocation_lines = []
    for row in rows:
        weight = (row["market_value"] / total_value * 100) if total_value else 0
        allocation_lines.append(
            f"- {row['ticker']}: {weight:.1f}% allocation, "
            f"value {money(row['market_value'])}, gain/loss {money(row['gain_loss'])}"
        )

    return {
        "answer": "\n".join(
            [
                "Portfolio analysis from local fallback seed data:",
                f"- Total value: {money(total_value)}",
                f"- Total gain/loss: {money(total_gain_loss)} ({total_gain_loss_percent:+.2f}%)",
                "",
                "Allocation:",
                *allocation_lines,
                "",
                "Risk alerts:",
                *[f"- {alert}" for alert in alerts],
                "",
                "Note: MCP is unavailable, so local seed portfolio data and direct Yahoo Finance quotes were used.",
            ]
        ),
        "total_value": total_value,
        "total_gain_loss": total_gain_loss,
        "total_gain_loss_percent": total_gain_loss_percent,
        "holdings": rows,
        "risk_alerts": alerts,
        "risk_alert_details": [classify_risk_alert(alert) for alert in alerts],
        "sources": ["Local fallback seed portfolio", "Yahoo Finance via yfinance fallback"],
    }


def user_context(user_id: str, question: str) -> dict[str, Any]:
    user = get_user_profile(user_id)
    if not user:
        return {
            "answer": f"No local seed user found for `{user_id}`.",
            "user_id": user_id,
            "watchlist": [],
            "sources": ["Local fallback seed users"],
        }
    if "watchlist" in question.lower():
        answer = f"Your watchlist contains: {', '.join(user['watchlist'])}."
    else:
        answer = (
            f"{user['display_name']} ({user_id}) has a {user['risk_profile']} risk profile, "
            f"focuses on {user['sector']}, and tracks {len(user['watchlist'])} stocks."
        )
    return {**user, "answer": answer, "sources": ["Local fallback seed users"]}
