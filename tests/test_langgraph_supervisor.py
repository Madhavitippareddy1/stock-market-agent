from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents import stock_agent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.graphs.langgraph_supervisor import LangGraphSupervisor
from stock_market_agent.services import metrics as metrics_module
from stock_market_agent.services.metrics import MetricsService
from stock_market_agent.config import Settings


class FakeMcpClient:
    def call_tool(self, tool_name, arguments):
        if tool_name == "stock_research":
            question = str(arguments.get("question", "")).lower()
            ticker = "CSCO"
            company = "Cisco Systems"
            if "pepsi" in question:
                ticker = "PEP"
                company = "PepsiCo"
            elif "apple" in question:
                ticker = "AAPL"
                company = "Apple"
            return {
                "answer": f"{ticker} - {company}: USD 50.00",
                "sources": ["Fake market data"],
                "tickers": [ticker],
                "quotes": [{"ticker": ticker, "price": 50.0, "currency": "USD"}],
                "arguments": arguments,
            }
        return {"answer": f"{tool_name} called", "sources": [], "arguments": arguments}


class FakeBedrock:
    def generate_text(self, *args, **kwargs):
        return "Bedrock investment summary"


def make_graph():
    client = FakeMcpClient()
    return LangGraphSupervisor(
        stock_agent=StockAgent(client),
        rag_agent=RagAgent(client),
        user_agent=UserAgent(client),
        portfolio_agent=PortfolioAgent(client),
        bedrock_service=FakeBedrock(),
    )


def test_langgraph_routes_stock_question():
    result = make_graph().run("Cisco Systems share price")
    assert result["agent"] == "Stock Agent"


def test_langgraph_routes_investment_question_to_bedrock_backed_agent():
    result = make_graph().run("should I buy PepsiCo?", user_id="demo-user")
    assert result["agent"] == "Investment Agent"
    assert "PEP" in result["answer"]
    assert "Stock evidence" in result["answer"]


def test_langgraph_routes_best_stock_question_to_investment_agent():
    result = make_graph().run("suggest me the best stock of this month", user_id="demo-user")
    assert result["agent"] == "Investment Agent"
    assert result["answer"] == "Bedrock investment summary"


def test_investment_question_keeps_requested_apple_ticker():
    result = make_graph().run("is better to invest in apple", user_id="demo-user")

    assert result["agent"] == "Investment Agent"
    assert "AAPL" in result["answer"]
    assert "SBUX" not in result["answer"]


def test_investment_question_with_budget_uses_budget_screen(monkeypatch):
    def fake_quote(ticker):
        prices = {
            "CSCO": 50.0,
            "PFE": 25.0,
            "KO": 70.0,
            "T": 30.0,
            "VZ": 45.0,
            "INTC": 35.0,
            "WBD": 12.0,
            "CMCSA": 40.0,
            "PYPL": 80.0,
            "SBUX": 110.0,
        }
        price = prices[ticker]
        return {
            "ticker": ticker,
            "company_name": f"{ticker} Company",
            "price": price,
            "previous_close": max(price - 1, 1),
            "currency": "USD",
            "market_cap": 100_000_000_000,
            "sector": "Technology",
            "industry": "Test industry",
        }

    monkeypatch.setattr(stock_agent, "_quote_from_yfinance", fake_quote)

    result = make_graph().run("best stock to invest now, i have £100", user_id="demo-user")

    assert result["agent"] == "Investment Agent"
    assert "Budget-aware investment screen" in result["answer"]
    assert "AAPL" not in result["answer"]
    assert (result["data"]["stock"] or {}).get("budget_screen") is True


def test_langgraph_records_stock_tickers_in_observability_metadata(tmp_path, monkeypatch):
    service = MetricsService(Settings(observability_metrics_path=str(tmp_path / "metrics.jsonl")))
    monkeypatch.setattr(metrics_module, "_metrics", service)

    result = make_graph().run("Cisco Systems share price", user_id="demo-user")
    summary = service.dashboard_summary()
    request_events = [event for event in summary["events"] if event["event_type"] == "request"]

    assert result["agent"] == "Stock Agent"
    assert request_events
    metadata = request_events[-1]["metadata"]
    assert metadata["tickers"] == ["CSCO"]
    assert metadata["stock_prices"][0]["ticker"] == "CSCO"
