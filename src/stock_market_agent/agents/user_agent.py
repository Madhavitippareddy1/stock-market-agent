from stock_market_agent.models import AgentResult
from stock_market_agent.services.mcp_client import McpClient


class UserAgent:
    def __init__(self, mcp_client: McpClient) -> None:
        self.mcp_client = mcp_client

    def answer(self, user_id: str, question: str) -> AgentResult:
        result = self.mcp_client.call_tool(
            "user_context",
            {"user_id": user_id, "question": question},
        )
        answer = result.get("answer") or f"User context is not configured yet for {user_id}."
        return AgentResult(agent="User Agent", answer=answer, data=result)
