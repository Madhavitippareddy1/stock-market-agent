from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import yfinance as yf

from stock_market_agent.config import get_settings
from stock_market_agent.services.chat_history import load_database_secret


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
CUSTOM_USERS_PATH = Path("data/custom_users.json")


def _database_credentials() -> tuple[str | None, int, str, str | None, str | None]:
    settings = get_settings()
    database_username = settings.database_username
    database_password = settings.database_password
    if settings.database_secret_arn and (not database_username or not database_password):
        try:
            secret = load_database_secret(settings.database_secret_arn, settings.aws_region)
            database_username = database_username or secret.get("username")
            database_password = database_password or secret.get("password")
        except Exception:
            database_username = None
            database_password = None
    return (
        settings.database_host,
        settings.database_port,
        settings.database_name,
        database_username,
        database_password,
    )


def _postgres_configured() -> bool:
    host, _, _, username, password = _database_credentials()
    return bool(host and username and password)


def _postgres_connect():
    host, port, dbname, username, password = _database_credentials()
    if not host or not username or not password:
        raise RuntimeError("PostgreSQL custom user store is not configured")
    return psycopg.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=username,
        password=password,
        connect_timeout=5,
    )


def _initialize_postgres_custom_store(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS investment_users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            sector TEXT NOT NULL,
            risk_profile TEXT NOT NULL,
            investment_goal TEXT NOT NULL,
            watchlist JSONB NOT NULL DEFAULT '[]'::jsonb,
            source TEXT NOT NULL DEFAULT 'streamlit-created',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS investment_portfolio_holdings (
            user_id TEXT NOT NULL REFERENCES investment_users(user_id) ON DELETE CASCADE,
            ticker TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            average_buy_price NUMERIC NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, ticker)
        )
        """
    )


def _coerce_watchlist(value: Any) -> list[str]:
    if isinstance(value, list):
        return _normalize_tickers(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return _normalize_tickers(parsed)
        except Exception:
            return _normalize_tickers(value)
    return []


def _load_postgres_custom_store() -> dict[str, Any]:
    with _postgres_connect() as connection:
        _initialize_postgres_custom_store(connection)
        user_rows = connection.execute(
            """
            SELECT user_id, display_name, sector, risk_profile, investment_goal, watchlist::TEXT, source
            FROM investment_users
            ORDER BY user_id ASC
            """
        ).fetchall()
        holding_rows = connection.execute(
            """
            SELECT user_id, ticker, quantity, average_buy_price
            FROM investment_portfolio_holdings
            ORDER BY user_id ASC, ticker ASC
            """
        ).fetchall()

    users = {
        row[0]: {
            "user_id": row[0],
            "display_name": row[1],
            "sector": row[2],
            "risk_profile": row[3],
            "investment_goal": row[4],
            "watchlist": _coerce_watchlist(row[5]),
            "source": row[6],
        }
        for row in user_rows
    }
    portfolios: dict[str, list[dict[str, Any]]] = {user_id: [] for user_id in users}
    for row in holding_rows:
        portfolios.setdefault(row[0], []).append(
            {
                "ticker": row[1],
                "quantity": float(row[2]),
                "average_buy_price": float(row[3]),
            }
        )
    return {"users": users, "portfolios": portfolios}


def _save_postgres_custom_store(store: dict[str, Any]) -> None:
    with _postgres_connect() as connection:
        _initialize_postgres_custom_store(connection)
        for user_id, user in store.get("users", {}).items():
            watchlist = _normalize_tickers(user.get("watchlist", []))
            connection.execute(
                """
                INSERT INTO investment_users(
                    user_id, display_name, sector, risk_profile, investment_goal, watchlist, source, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    sector = EXCLUDED.sector,
                    risk_profile = EXCLUDED.risk_profile,
                    investment_goal = EXCLUDED.investment_goal,
                    watchlist = EXCLUDED.watchlist,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    user.get("display_name", "New Investor"),
                    user.get("sector", "diversified"),
                    user.get("risk_profile", "balanced"),
                    user.get("investment_goal", "long-term growth"),
                    json.dumps(watchlist),
                    user.get("source", "streamlit-created"),
                ),
            )
            connection.execute(
                "DELETE FROM investment_portfolio_holdings WHERE user_id = %s",
                (user_id,),
            )
            for holding in store.get("portfolios", {}).get(user_id, []):
                connection.execute(
                    """
                    INSERT INTO investment_portfolio_holdings(
                        user_id, ticker, quantity, average_buy_price, updated_at
                    )
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id, ticker) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        average_buy_price = EXCLUDED.average_buy_price,
                        updated_at = NOW()
                    """,
                    (
                        user_id,
                        str(holding.get("ticker", "")).upper(),
                        float(holding.get("quantity", 0)),
                        float(holding.get("average_buy_price", 0)),
                    ),
                )


def _normalize_tickers(tickers: list[str] | str | None) -> list[str]:
    if tickers is None:
        return []
    if isinstance(tickers, str):
        raw_items = re.split(r"[\s,]+", tickers)
    else:
        raw_items = tickers
    normalized: list[str] = []
    for item in raw_items:
        ticker = str(item).strip().upper()
        if ticker and re.fullmatch(r"[A-Z.]{1,6}", ticker) and ticker not in normalized:
            normalized.append(ticker)
    return normalized[:10]


def _load_custom_store() -> dict[str, Any]:
    if _postgres_configured():
        try:
            return _load_postgres_custom_store()
        except Exception:
            # Local development should keep working even when the private RDS
            # endpoint is not reachable from the developer machine.
            pass
    if not CUSTOM_USERS_PATH.exists():
        return {"users": {}, "portfolios": {}}
    try:
        with CUSTOM_USERS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception:
        return {"users": {}, "portfolios": {}}
    return {
        "users": data.get("users", {}),
        "portfolios": data.get("portfolios", {}),
    }


def _save_custom_store(store: dict[str, Any]) -> None:
    if _postgres_configured():
        try:
            _save_postgres_custom_store(store)
            return
        except Exception:
            # Fall back to local JSON if a developer is outside the VPC or AWS
            # credentials are unavailable. ECS uses RDS when reachable.
            pass
    CUSTOM_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CUSTOM_USERS_PATH.open("w", encoding="utf-8") as file:
        json.dump(store, file, indent=2, sort_keys=True)


def list_custom_users() -> list[dict[str, Any]]:
    store = _load_custom_store()
    return [store["users"][user_id] for user_id in sorted(store["users"])]


def create_investment_user(
    *,
    display_name: str,
    sector: str,
    risk_profile: str,
    investment_goal: str,
    watchlist: list[str] | str,
) -> dict[str, Any]:
    clean_name = display_name.strip() or "New Investor"
    clean_sector = sector.strip().lower() or "diversified"
    clean_risk = risk_profile.strip().lower() or "balanced"
    clean_goal = investment_goal.strip() or "long-term growth"
    clean_watchlist = _normalize_tickers(watchlist) or ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "new-user"

    store = _load_custom_store()
    users = store["users"]
    portfolios = store["portfolios"]
    base_user_id = f"custom-{slug}"
    user_id = base_user_id
    suffix = 1
    while user_id in users or user_id in SEED_USERS:
        suffix += 1
        user_id = f"{base_user_id}-{suffix}"

    user = {
        "user_id": user_id,
        "display_name": clean_name,
        "sector": clean_sector,
        "risk_profile": clean_risk,
        "investment_goal": clean_goal,
        "watchlist": clean_watchlist,
        "source": "streamlit-created",
    }
    users[user_id] = user
    portfolios[user_id] = [
        {
            "ticker": ticker,
            "quantity": 3 + index,
            "average_buy_price": float(90 + (index * 22)),
        }
        for index, ticker in enumerate(clean_watchlist, start=1)
    ]
    _save_custom_store(store)
    return user


def list_investment_users() -> list[dict[str, Any]]:
    seed_users = [SEED_USERS[user_id] for user_id in sorted(SEED_USERS) if user_id != "demo-user"]
    return [*seed_users, *list_custom_users()]


def get_user_profile(user_id: str) -> dict[str, Any] | None:
    if user_id in SEED_USERS:
        return SEED_USERS[user_id]
    return _load_custom_store()["users"].get(user_id)


def get_user_portfolio(user_id: str) -> list[dict[str, Any]]:
    if user_id in SEED_PORTFOLIOS:
        return SEED_PORTFOLIOS[user_id]
    return _load_custom_store()["portfolios"].get(user_id, [])


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
