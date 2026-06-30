from stock_market_agent.models import PortfolioHolding


def concentration_alerts(
    holdings: list[PortfolioHolding],
    prices: dict[str, float],
    *,
    max_single_position_percent: float = 35.0,
) -> list[str]:
    values = {
        holding.ticker: holding.quantity * prices.get(holding.ticker, 0.0)
        for holding in holdings
    }
    total_value = sum(values.values())
    if total_value <= 0:
        return ["Portfolio value is zero or prices are unavailable."]

    alerts: list[str] = []
    for ticker, value in values.items():
        weight = (value / total_value) * 100
        if weight > max_single_position_percent:
            alerts.append(
                f"{ticker} is {weight:.1f}% of the portfolio, above the "
                f"{max_single_position_percent:.1f}% concentration limit."
            )

    return alerts
