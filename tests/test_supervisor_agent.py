from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.supervisor_agent import SupervisorAgent
from stock_market_agent.agents.user_agent import UserAgent


class FakeMcpClient:
    def call_tool(self, tool_name, arguments):
        return {"answer": f"{tool_name} called", "arguments": arguments}


def make_supervisor():
    client = FakeMcpClient()
    return SupervisorAgent(
        stock_agent=StockAgent(client),
        rag_agent=RagAgent(client),
        user_agent=UserAgent(client),
        portfolio_agent=PortfolioAgent(client),
    )


def test_routes_stock_question_to_stock_agent():
    result = make_supervisor().run("what is Apple stock price?")
    assert result["agent"] == "Stock Agent"


def test_routes_portfolio_question_to_portfolio_agent():
    result = make_supervisor().run("analyze my portfolio")
    assert result["agent"] == "Portfolio Agent"


def test_routes_watchlist_question_to_user_agent():
    result = make_supervisor().run("show my watchlist")
    assert result["agent"] == "User Agent"


def test_routes_report_question_to_rag_agent():
    result = make_supervisor().run("analyse this report")
    assert result["agent"] == "RAG Agent"
