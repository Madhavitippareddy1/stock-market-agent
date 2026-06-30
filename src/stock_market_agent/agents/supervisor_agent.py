from typing import Any

from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent


class SupervisorAgent:
    def __init__(
        self,
        stock_agent: StockAgent,
        rag_agent: RagAgent,
        user_agent: UserAgent,
        portfolio_agent: PortfolioAgent,
    ) -> None:
        self.stock_agent = stock_agent
        self.rag_agent = rag_agent
        self.user_agent = user_agent
        self.portfolio_agent = portfolio_agent

    def run(
        self,
        question: str,
        *,
        user_id: str = "demo-user",
        uploaded_file: Any | None = None,
    ) -> dict[str, Any]:
        normalized = question.lower()

        if uploaded_file is not None or any(word in normalized for word in ["report", "pdf", "document"]):
            return self.rag_agent.answer(question=question, uploaded_file=uploaded_file).model_dump()

        if "portfolio" in normalized or "holding" in normalized or "risk alert" in normalized:
            return self.portfolio_agent.answer(user_id=user_id, question=question).model_dump()

        if "watchlist" in normalized or "risk profile" in normalized or "my profile" in normalized:
            return self.user_agent.answer(user_id=user_id, question=question).model_dump()

        return self.stock_agent.answer(question=question).model_dump()
