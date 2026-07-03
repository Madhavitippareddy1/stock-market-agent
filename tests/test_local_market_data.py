from stock_market_agent.services import local_market_data


def test_local_seed_users_have_50_named_investors_with_10_stock_watchlists(tmp_path, monkeypatch):
    monkeypatch.setattr(local_market_data, "CUSTOM_USERS_PATH", tmp_path / "missing-custom-users.json")
    users = local_market_data.list_investment_users()

    assert len(users) == 50
    assert users[0]["display_name"]
    assert users[0]["user_id"].startswith("user-")
    assert all(len(user["watchlist"]) == 10 for user in users)


def test_each_seed_user_has_10_portfolio_holdings(tmp_path, monkeypatch):
    monkeypatch.setattr(local_market_data, "CUSTOM_USERS_PATH", tmp_path / "missing-custom-users.json")
    for user in local_market_data.list_investment_users():
        holdings = local_market_data.get_user_portfolio(user["user_id"])

        assert len(holdings) == 10
        assert all(holding["ticker"] for holding in holdings)
        assert all(holding["quantity"] > 0 for holding in holdings)
