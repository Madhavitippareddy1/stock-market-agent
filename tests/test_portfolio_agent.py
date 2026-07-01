from stock_market_agent.agents import portfolio_agent
from stock_market_agent.agents.portfolio_agent import PortfolioAgent


class FailingMcpClient:
    def call_tool(self, tool_name, arguments):
        return {
            "answer": f"MCP tool `{tool_name}` is unavailable: test failure",
            "tool": tool_name,
            "arguments": arguments,
        }


def test_portfolio_agent_uses_local_fallback_when_mcp_fails(monkeypatch):
    monkeypatch.setattr(
        portfolio_agent,
        "portfolio_analysis",
        lambda user_id: {
            "answer": f"Portfolio analysis from local fallback seed data for {user_id}",
            "total_value": 1234.0,
            "holdings": [{"ticker": "AAPL"}],
            "risk_alerts": ["No major concentration risk found."],
            "risk_alert_details": [{"severity": "low", "message": "No major concentration risk found."}],
            "sources": ["Local fallback seed portfolio"],
        },
    )

    result = PortfolioAgent(FailingMcpClient()).answer(
        "user-technology-001",
        "analyze my portfolio",
    )

    assert result.agent == "Portfolio Agent"
    assert "local fallback" in result.answer
    assert result.data["total_value"] == 1234.0
    assert result.sources == ["Local fallback seed portfolio"]
