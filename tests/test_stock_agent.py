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


def test_stock_agent_budget_screen_prefers_affordable_stock(monkeypatch):
    quotes = {
        "CSCO": {
            "ticker": "CSCO",
            "company_name": "Cisco Systems",
            "price": 50.0,
            "previous_close": 49.0,
            "currency": "USD",
            "market_cap": 200_000_000_000,
            "sector": "Technology",
            "industry": "Communication Equipment",
        },
        "PFE": {
            "ticker": "PFE",
            "company_name": "Pfizer Inc.",
            "price": 25.0,
            "previous_close": 26.0,
            "currency": "USD",
            "market_cap": 140_000_000_000,
            "sector": "Healthcare",
            "industry": "Drug Manufacturers",
        },
        "KO": {
            "ticker": "KO",
            "company_name": "Coca-Cola",
            "price": 70.0,
            "previous_close": 69.0,
            "currency": "USD",
            "market_cap": 300_000_000_000,
            "sector": "Consumer Defensive",
            "industry": "Beverages",
        },
        "T": {
            "ticker": "T",
            "company_name": "AT&T",
            "price": 30.0,
            "previous_close": 30.0,
            "currency": "USD",
            "market_cap": 210_000_000_000,
            "sector": "Communication Services",
            "industry": "Telecom",
        },
        "VZ": {
            "ticker": "VZ",
            "company_name": "Verizon",
            "price": 45.0,
            "previous_close": 44.0,
            "currency": "USD",
            "market_cap": 190_000_000_000,
            "sector": "Communication Services",
            "industry": "Telecom",
        },
        "INTC": {
            "ticker": "INTC",
            "company_name": "Intel",
            "price": 35.0,
            "previous_close": 35.0,
            "currency": "USD",
            "market_cap": 150_000_000_000,
            "sector": "Technology",
            "industry": "Semiconductors",
        },
        "WBD": {
            "ticker": "WBD",
            "company_name": "Warner Bros. Discovery",
            "price": 12.0,
            "previous_close": 12.5,
            "currency": "USD",
            "market_cap": 30_000_000_000,
            "sector": "Communication Services",
            "industry": "Entertainment",
        },
        "CMCSA": {
            "ticker": "CMCSA",
            "company_name": "Comcast",
            "price": 40.0,
            "previous_close": 39.0,
            "currency": "USD",
            "market_cap": 160_000_000_000,
            "sector": "Communication Services",
            "industry": "Telecom",
        },
        "PYPL": {
            "ticker": "PYPL",
            "company_name": "PayPal",
            "price": 80.0,
            "previous_close": 79.0,
            "currency": "USD",
            "market_cap": 90_000_000_000,
            "sector": "Financial Services",
            "industry": "Credit Services",
        },
        "SBUX": {
            "ticker": "SBUX",
            "company_name": "Starbucks",
            "price": 110.0,
            "previous_close": 111.0,
            "currency": "USD",
            "market_cap": 120_000_000_000,
            "sector": "Consumer Cyclical",
            "industry": "Restaurants",
        },
    }
    monkeypatch.setattr(stock_agent, "_quote_from_yfinance", lambda ticker: quotes[ticker])

    result = StockAgent(FailingMcpClient()).answer("best stock to invest now, i have £100")

    assert result.agent == "Stock Agent"
    assert result.data["budget_screen"] is True
    assert "Budget-aware investment screen" in result.answer
    assert "fractional shares" in result.answer
