from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.graphs.langgraph_supervisor import LangGraphSupervisor
from stock_market_agent.services import metrics as metrics_module
from stock_market_agent.services.metrics import MetricsService
from stock_market_agent.config import Settings


class FakeMcpClient:
    def call_tool(self, tool_name, arguments):
        if tool_name == "stock_research":
            return {
                "answer": "CSCO: USD 50.00",
                "sources": ["Fake market data"],
                "tickers": ["CSCO"],
                "quotes": [{"ticker": "CSCO", "price": 50.0, "currency": "USD"}],
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
    assert result["answer"] == "Bedrock investment summary"


def test_langgraph_routes_best_stock_question_to_investment_agent():
    result = make_graph().run("suggest me the best stock of this month", user_id="demo-user")
    assert result["agent"] == "Investment Agent"
    assert result["answer"] == "Bedrock investment summary"


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
