from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.config import get_settings
from stock_market_agent.graphs.langgraph_supervisor import LangGraphSupervisor
from stock_market_agent.services.chat_history import ChatHistoryService
from stock_market_agent.services.local_market_data import (
    create_investment_user,
    get_quote,
    list_investment_users,
    user_context as local_user_context,
)
from stock_market_agent.services.mcp_client import McpClient
from stock_market_agent.services.metrics import get_metrics_service


TOP_10_STOCKS = ["NVDA", "GOOGL", "AAPL", "MSFT", "AMZN", "META", "AVGO", "TSLA", "COST", "NFLX"]


class ResearchRequest(BaseModel):
    question: str
    user_id: str = "demo-user"
    conversation_context: str = ""
    save_history: bool = True


class PortfolioRequest(BaseModel):
    user_id: str = "demo-user"
    question: str = "analyze my portfolio"


class UserContextRequest(BaseModel):
    user_id: str = "demo-user"
    question: str = "show my profile"


class CreateUserRequest(BaseModel):
    display_name: str
    sector: str = "diversified"
    risk_profile: str = "balanced"
    investment_goal: str = "long-term growth"
    watchlist: list[str] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    session_id: str = "demo-user"
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, str]] = Field(default_factory=list)


@dataclass
class AppServices:
    mcp_client: McpClient
    supervisor: LangGraphSupervisor
    portfolio_agent: PortfolioAgent
    user_agent: UserAgent
    chat_history: Any


class UploadedFileAdapter:
    """Adapter so the existing RAG Agent can read FastAPI uploaded files."""

    def __init__(self, name: str, content_type: str | None, data: bytes) -> None:
        self.name = name
        self.type = content_type or "application/octet-stream"
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


_services: AppServices | None = None


def get_services() -> AppServices:
    global _services
    if _services is None:
        settings = get_settings()
        mcp_client = McpClient.from_settings()
        portfolio_agent = PortfolioAgent(mcp_client)
        user_agent = UserAgent(mcp_client)
        _services = AppServices(
            mcp_client=mcp_client,
            portfolio_agent=portfolio_agent,
            user_agent=user_agent,
            chat_history=ChatHistoryService.from_settings(settings),
            supervisor=LangGraphSupervisor(
                stock_agent=StockAgent(mcp_client),
                rag_agent=RagAgent(mcp_client),
                user_agent=user_agent,
                portfolio_agent=portfolio_agent,
            ),
        )
    return _services


app = FastAPI(
    title="Stock Market Agent API",
    version="0.1.0",
    description="FastAPI backend for the Stock Market Agent Streamlit frontend.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stock-market-agent-api"}


@app.get("/config")
def config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "aws_region": settings.aws_region,
        "mcp_server_url": settings.mcp_server_url,
        "reports_bucket_configured": bool(settings.reports_bucket),
        "opensearch_configured": bool(settings.opensearch_endpoint),
        "langfuse_enabled": settings.langfuse_enabled,
        "ragas_enabled": settings.ragas_enabled,
    }


@app.post("/research")
def research(request: ResearchRequest) -> dict[str, Any]:
    services = get_services()
    history_context = (
        services.chat_history.build_context(request.user_id) if request.save_history else ""
    )
    combined_context = "\n".join(
        item for item in [request.conversation_context, history_context] if item
    )
    if request.save_history:
        services.chat_history.add_message(request.user_id, "user", request.question)
    result = services.supervisor.run(
        question=request.question,
        user_id=request.user_id,
        conversation_context=combined_context,
    )
    if request.save_history:
        services.chat_history.add_message(request.user_id, "assistant", result.get("answer", ""))
    return result


@app.post("/research/upload")
async def research_upload(
    question: str = Form(...),
    user_id: str = Form("demo-user"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    services = get_services()
    data = await file.read()
    uploaded = UploadedFileAdapter(file.filename or "uploaded-report", file.content_type, data)
    services.chat_history.add_message(user_id, "user", question)
    result = services.supervisor.run(question=question, user_id=user_id, uploaded_file=uploaded)
    services.chat_history.add_message(user_id, "assistant", result.get("answer", ""))
    return result


@app.post("/portfolio/analyze")
def portfolio(request: PortfolioRequest) -> dict[str, Any]:
    return get_services().portfolio_agent.answer(request.user_id, request.question).model_dump()


@app.post("/user/context")
def user_context(request: UserContextRequest) -> dict[str, Any]:
    return get_services().user_agent.answer(request.user_id, request.question).model_dump()


@app.get("/users")
def users() -> dict[str, Any]:
    result = get_services().mcp_client.call_tool("list_investment_users", {})
    answer = str(result.get("answer", "")).lower()
    if "mcp tool" in answer and any(
        marker in answer for marker in ["unavailable", "timed out", "not configured", "returned no content"]
    ):
        return {"users": list_investment_users(), "sources": ["Local fallback users"]}
    local_users = list_investment_users()
    existing_ids = {user.get("user_id") for user in result.get("users", [])}
    custom_users = [
        user
        for user in local_users
        if user.get("source") == "streamlit-created" and user.get("user_id") not in existing_ids
    ]
    if custom_users:
        result["users"] = [*(result.get("users") or []), *custom_users]
    return result


@app.post("/users")
def create_user(request: CreateUserRequest) -> dict[str, Any]:
    user = create_investment_user(
        display_name=request.display_name,
        sector=request.sector,
        risk_profile=request.risk_profile,
        investment_goal=request.investment_goal,
        watchlist=request.watchlist,
    )
    return {
        "user": user,
        "profile": local_user_context(user["user_id"], "show my profile"),
        "sources": ["Local custom user store"],
    }


@app.get("/watchlist/{user_id}")
def watchlist(user_id: str) -> dict[str, Any]:
    result = get_services().mcp_client.call_tool("get_user_watchlist", {"user_id": user_id})
    answer = str(result.get("answer", "")).lower()
    if "mcp tool" in answer and any(
        marker in answer for marker in ["unavailable", "timed out", "not configured", "returned no content"]
    ):
        profile = local_user_context(user_id, "show my watchlist")
        local_watchlist = profile.get("watchlist") or (profile.get("user") or {}).get("watchlist", [])
        return {
            "user_id": user_id,
            "watchlist": local_watchlist,
            "answer": profile.get("answer", ""),
            "sources": profile.get("sources", ["Local fallback users"]),
        }
    if not result.get("watchlist"):
        profile = local_user_context(user_id, "show my watchlist")
        local_watchlist = profile.get("watchlist") or (profile.get("user") or {}).get("watchlist", [])
        if local_watchlist:
            return {
                "user_id": user_id,
                "watchlist": local_watchlist,
                "answer": profile.get("answer", ""),
                "sources": profile.get("sources", ["Local fallback users"]),
            }
    return result


@app.get("/stock/quotes")
def stock_quotes(tickers: list[str] = Query(default=[])) -> dict[str, Any]:
    clean_tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    quotes = [get_quote(ticker).__dict__ for ticker in clean_tickers]
    return {"tickers": clean_tickers, "quotes": quotes, "sources": ["Yahoo Finance via yfinance"]}


@app.get("/stock/top10")
def stock_top10() -> dict[str, Any]:
    quotes = [get_quote(ticker).__dict__ for ticker in TOP_10_STOCKS]
    return {"tickers": TOP_10_STOCKS, "quotes": quotes, "sources": ["Yahoo Finance via yfinance"]}


@app.get("/chat/{session_id}")
def chat_history(session_id: str, limit: int = 30) -> ChatHistoryResponse:
    messages = get_services().chat_history.get_messages(session_id, limit=limit)
    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            {"role": message.role, "content": message.content, "created_at": message.created_at}
            for message in messages
        ],
    )


@app.delete("/chat/{session_id}")
def clear_chat_history(session_id: str) -> dict[str, str]:
    get_services().chat_history.clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@app.get("/observability/summary")
def observability_summary() -> dict[str, Any]:
    return get_metrics_service().dashboard_summary()
