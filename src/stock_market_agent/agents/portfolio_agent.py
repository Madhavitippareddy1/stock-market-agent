from stock_market_agent.models import AgentResult
from stock_market_agent.services.mcp_client import McpClient
from stock_market_agent.services.local_market_data import portfolio_analysis


def _is_mcp_error(result: dict) -> bool:
    answer = str(result.get("answer", "")).lower()
    return (
        "mcp tool" in answer
        and any(
            marker in answer
            for marker in ["unavailable", "timed out", "not configured", "returned no content"]
        )
    ) or "no portfolio holdings found" in answer


class PortfolioAgent:
    def __init__(self, mcp_client: McpClient) -> None:
        self.mcp_client = mcp_client

    def answer(self, user_id: str, question: str) -> AgentResult:
        result = self.mcp_client.call_tool(
            "portfolio_analysis",
            {"user_id": user_id, "question": question},
        )
        if _is_mcp_error(result):
            result = portfolio_analysis(user_id)
        answer = result.get("answer") or "Portfolio analysis tool is not configured yet."
        return AgentResult(
            agent="Portfolio Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )
