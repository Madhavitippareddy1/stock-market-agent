from fastapi.testclient import TestClient

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


def test_portfolio_endpoint_returns_result():
    response = client.post(
        "/portfolio/analyze",
        json={"user_id": "demo-user", "question": "analyze my portfolio"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "Portfolio Agent"
    assert "answer" in payload