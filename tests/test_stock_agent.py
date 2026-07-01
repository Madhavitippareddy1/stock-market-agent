from stock_market_agent.agents import stock_agent
from stock_market_agent.agents.stock_agent import StockAgent


class FailingMcpClient:
    def call_tool(self, tool_name, arguments):
        return {
            "answer": f"MCP tool `{tool_name}` is unavailable: test failure",
            "tool": tool_name,
            "arguments": arguments,
        }


def test_stock_agent_falls_back_when_mcp_tool_fails(monkeypatch):
    quotes = {
        "AAPL": {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "price": 200.0,
            "previous_close": 190.0,
            "currency": "USD",
            "market_cap": 3_000_000_000_000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        },
        "AMZN": {
            "ticker": "AMZN",
            "company_name": "Amazon.com, Inc.",
            "price": 180.0,
            "previous_close": 181.0,
            "currency": "USD",
            "market_cap": 2_000_000_000_000,
            "sector": "Consumer Cyclical",
            "industry": "Internet Retail",
        },
    }

    monkeypatch.setattr(stock_agent, "_quote_from_yfinance", lambda ticker: quotes[ticker])

    result = StockAgent(FailingMcpClient()).answer("compare apple and amazon")

    assert result.agent == "Stock Agent"
    assert "Stock comparison from direct fallback data" in result.answer
    assert result.answer.index("AAPL") < result.answer.index("AMZN")
    assert result.data["tickers"] == ["AAPL", "AMZN"]
    assert result.sources == ["Yahoo Finance via yfinance fallback"]
