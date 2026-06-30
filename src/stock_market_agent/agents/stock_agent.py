from stock_market_agent.models import AgentResult
from stock_market_agent.services.mcp_client import McpClient


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
        answer = result.get("answer") or "Stock research tool did not return an answer yet."
        return AgentResult(
            agent="Stock Agent",
            answer=answer,
            sources=result.get("sources", []),
            data=result,
        )
