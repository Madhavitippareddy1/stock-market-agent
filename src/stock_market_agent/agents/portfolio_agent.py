from stock_market_agent.models import AgentResult
from stock_market_agent.services.mcp_client import McpClient


class PortfolioAgent:
    def __init__(self, mcp_client: McpClient) -> None:
        self.mcp_client = mcp_client

    def answer(self, user_id: str, question: str) -> AgentResult:
        result = self.mcp_client.call_tool(
            "portfolio_analysis",
            {"user_id": user_id, "question": question},
        )
        answer = result.get("answer") or "Portfolio analysis tool is not configured yet."
        return AgentResult(
            agent="Portfolio Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )
