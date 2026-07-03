from types import SimpleNamespace

from fastapi.testclient import TestClient

from stock_market_agent import api as api_module
from stock_market_agent.api import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_endpoint():
    response = client.get("/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app_name"] == "stock-market-agent"
    assert "mcp_server_url" in payload


def test_research_endpoint_returns_agent_result():
    response = client.post(
        "/research",
        json={"question": "Cisco Systems share price", "user_id": "api-test-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] in {"Stock Agent", "Investment Agent", "RAG Agent", "Portfolio Agent", "User Agent"}
    assert payload["answer"]


def test_research_endpoint_can_skip_chat_history(monkeypatch):
    class DummyChatHistory:
        def __init__(self):
            self.context_requested = False
            self.saved_messages = []

        def build_context(self, user_id: str) -> str:
            self.context_requested = True
            return f"old context for {user_id}"

        def add_message(self, user_id: str, role: str, content: str) -> None:
            self.saved_messages.append((user_id, role, content))

    class DummySupervisor:
        def __init__(self):
            self.received_context = None

        def run(self, question: str, user_id: str, conversation_context: str) -> dict:
            self.received_context = conversation_context
            return {"agent": "Stock Agent", "answer": f"Answer for {question}", "sources": []}

    chat_history = DummyChatHistory()
    supervisor = DummySupervisor()
    monkeypatch.setattr(
        api_module,
        "_services",
        SimpleNamespace(chat_history=chat_history, supervisor=supervisor),
    )

    response = client.post(
        "/research",
        json={
            "question": "Walmart stock price",
            "user_id": "stock-chat",
            "save_history": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["agent"] == "Stock Agent"
    assert chat_history.context_requested is False
    assert chat_history.saved_messages == []
    assert supervisor.received_context == ""


def test_portfolio_endpoint_returns_result():
    response = client.post(
        "/portfolio/analyze",
        json={"user_id": "demo-user", "question": "analyze my portfolio"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "Portfolio Agent"
    assert "answer" in payload
