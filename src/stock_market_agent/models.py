from typing import Any

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    agent: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class StockQuote(BaseModel):
    ticker: str
    price: float | None = None
    previous_close: float | None = None
    currency: str | None = None
    market_cap: float | None = None


class PortfolioHolding(BaseModel):
    ticker: str
    quantity: float
    average_buy_price: float


class UserProfile(BaseModel):
    user_id: str
    risk_profile: str = "balanced"
    investment_goal: str = "long-term research"
    watchlist: list[str] = Field(default_factory=list)
