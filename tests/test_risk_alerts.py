from stock_market_agent.models import PortfolioHolding
from stock_market_agent.tools.risk_alerts import concentration_alerts


def test_concentration_alerts_flags_large_position():
    holdings = [
        PortfolioHolding(ticker="AAPL", quantity=10, average_buy_price=100),
        PortfolioHolding(ticker="MSFT", quantity=1, average_buy_price=100),
    ]
    alerts = concentration_alerts(holdings, {"AAPL": 200, "MSFT": 100})
    assert any("AAPL" in alert for alert in alerts)
