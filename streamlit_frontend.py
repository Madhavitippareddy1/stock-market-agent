from __future__ import annotations

import os
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8002").rstrip("/")
DISCLAIMER = (
    "Disclaimer: This app is for educational stock research only. It is not "
    "financial, investment, legal, or tax advice. Please verify data and consult "
    "a licensed financial advisor before making investment decisions."
)


def api_get(path: str, **params: Any) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=180)
    response.raise_for_status()
    return response.json()


def api_delete(path: str) -> dict[str, Any]:
    response = requests.delete(f"{API_BASE_URL}{path}", timeout=60)
    response.raise_for_status()
    return response.json()


def init_state() -> None:
    defaults: dict[str, Any] = {
        "research_result": None,
        "portfolio_result": None,
        "watchlist_result": None,
        "users_result": None,
        "observability_result": None,
        "chatbot_result": None,
        "last_agent_call": "None",
        "last_agent_flow": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 2.2rem;
            max-width: 1280px;
        }
        h1 {
            font-size: 3.1rem !important;
            font-weight: 850 !important;
        }
        h2, h3 {
            font-weight: 800 !important;
        }
        p, label, span, div, button, input, textarea {
            font-size: 1.02rem;
        }
        [data-testid="stSidebar"] {
            background: #101828;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span {
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] button {
            background-color: #ffffff !important;
            color: #101828 !important;
            border: 1px solid #d0d5dd !important;
            font-weight: 800 !important;
        }
        div[data-testid="stTabs"] button {
            font-weight: 750;
            font-size: 1.05rem;
        }
        .hero-card {
            padding: 2rem;
            border-radius: 1.25rem;
            color: #ffffff;
            background: linear-gradient(120deg, #14213d, #ff4b4b);
            margin-bottom: 1.2rem;
            box-shadow: 0 22px 45px rgba(16, 24, 40, 0.14);
        }
        .hero-card p {
            color: #ffffff !important;
            font-size: 1.25rem;
        }
        .disclaimer {
            background: #e8f2ff;
            color: #084b8a;
            padding: 1rem 1.2rem;
            border-radius: 0.75rem;
            margin-top: 1rem;
            line-height: 1.55;
        }
        .chat-panel {
            background: #18243a;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 1rem;
            padding: 1rem;
            margin: 0.75rem 0 1rem 0;
        }
        .flow-card {
            background: #f8fafc;
            border: 1px solid #e4e7ec;
            border-radius: 0.9rem;
            padding: 0.9rem 1rem;
            margin: 0.65rem 0;
            color: #101828;
        }
        .flow-card strong {
            color: #101828;
        }
        .flow-route {
            color: #d92d20;
            font-weight: 800;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer() -> None:
    st.markdown(f'<div class="disclaimer">{DISCLAIMER}</div>', unsafe_allow_html=True)


def render_stock_history_chart(result: dict[str, Any]) -> None:
    data = result.get("data") or {}
    history = data.get("history") or (data.get("stock") or {}).get("history") or {}
    rows: list[dict[str, Any]] = []
    for ticker, monthly_rows in history.items():
        for row in monthly_rows or []:
            if row.get("month") and row.get("close") is not None:
                rows.append({"ticker": ticker, **row})
    if not rows:
        return

    df = pd.DataFrame(rows)
    df["month"] = pd.to_datetime(df["month"])
    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("close:Q", title="Monthly close", scale=alt.Scale(zero=False)),
            color="ticker:N",
            tooltip=[
                "ticker",
                alt.Tooltip("month:T", format="%Y-%m"),
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        )
        .properties(height=360)
    )
    st.markdown("### 5-year monthly close chart")
    st.altair_chart(chart, width="stretch")
    with st.expander("Monthly history table", expanded=False):
        table = df.copy()
        table["month"] = table["month"].dt.strftime("%Y-%m")
        st.dataframe(table, width="stretch", hide_index=True)


def render_agent_result(result: dict[str, Any] | None) -> None:
    if not result:
        return
    st.subheader(result.get("agent", "Agent"))
    st.markdown(result.get("answer", "No answer returned."))
    render_stock_history_chart(result)
    if result.get("sources"):
        with st.expander("Sources", expanded=False):
            st.write(result["sources"])
    render_disclaimer()


def render_compact_agent_result(result: dict[str, Any] | None) -> None:
    if not result:
        return
    st.caption(result.get("agent", "Agent"))
    answer = result.get("answer", "No answer returned.")
    if len(answer) > 1800:
        answer = f"{answer[:1800].rstrip()}..."
    st.markdown(answer)
    if result.get("sources"):
        st.caption(f"Sources: {len(result['sources'])}")
    render_disclaimer()


def render_chat_history(session_id: str, limit: int = 8) -> None:
    try:
        history = api_get(f"/chat/{session_id}", limit=limit)
    except Exception as exc:
        st.warning(f"Chat history unavailable: {exc}")
        return

    messages = history.get("messages", [])
    if not messages:
        st.info("No chat history yet.")
        return

    for message in messages[-limit:]:
        role = "user" if message.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.get("content", ""))
            if message.get("created_at"):
                st.caption(message["created_at"])


def get_agent_flow(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    data = result.get("data") or {}
    flow = data.get("agent_flow")
    if isinstance(flow, dict):
        return flow

    agent = result.get("agent", "Agent")
    route = agent.lower().replace(" agent", "").replace(" ", "_")
    return {
        "supervisor": "Supervisor Agent",
        "route": route,
        "selected_agent": agent,
        "sub_agents": [agent],
        "steps": [
            "User question/upload received",
            "Supervisor Agent routed the request",
            f"Final response returned by {agent}",
        ],
    }


def render_agent_flow(result: dict[str, Any] | None, title: str = "Supervisor and sub-agent flow") -> None:
    flow = get_agent_flow(result)
    if not flow:
        st.info("No agent flow yet. Ask a question or upload a document to see the route.")
        return

    sub_agents = flow.get("sub_agents") or [flow.get("selected_agent", "Agent")]
    steps = flow.get("steps") or []

    st.markdown(f"### {title}")
    st.markdown(
        f"""
        <div class="flow-card">
            <strong>User request</strong> -> <strong>{flow.get("supervisor", "Supervisor Agent")}</strong>
            -> <span class="flow-route">{flow.get("route", "route")}</span>
            -> <strong>{flow.get("selected_agent", "Agent")}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    flow_rows = [
        {"step": "1", "component": "User", "action": "Submits a question or uploaded file"},
        {"step": "2", "component": "Supervisor Agent", "action": "Classifies the request and chooses the route"},
    ]
    for index, agent_name in enumerate(sub_agents, start=3):
        flow_rows.append(
            {
                "step": str(index),
                "component": agent_name,
                "action": "Runs the selected tool/analysis for this request",
            }
        )
    flow_rows.append(
        {
            "step": str(len(flow_rows) + 1),
            "component": "Streamlit UI",
            "action": "Renders the answer, sources, charts, and disclaimer",
        }
    )
    st.dataframe(pd.DataFrame(flow_rows), width="stretch", hide_index=True)

    if steps:
        with st.expander("Detailed route steps", expanded=False):
            for step in steps:
                st.write(f"- {step}")


def load_seed_users() -> list[dict[str, Any]]:
    if not st.session_state.get("users_result"):
        try:
            st.session_state["users_result"] = api_get("/users")
        except Exception:
            st.session_state["users_result"] = {"users": []}
    return st.session_state.get("users_result", {}).get("users", [])


def user_label(user: dict[str, Any]) -> str:
    name = user.get("display_name") or "Unknown user"
    user_id = user.get("user_id") or ""
    sector = user.get("sector") or "sector"
    return f"{name} - {user_id} ({sector})"


def render_user_picker(default_user_id: str, key_prefix: str) -> tuple[str, dict[str, Any] | None]:
    users = load_seed_users()
    if not users:
        manual_user = st.text_input(
            "User ID",
            value=default_user_id,
            key=f"{key_prefix}_manual_user",
        )
        return manual_user, None

    options = [user_label(user) for user in users]
    default_index = 0
    for index, user in enumerate(users):
        if user.get("user_id") == default_user_id:
            default_index = index
            break
    selected_label = st.selectbox(
        "Select seeded user",
        options=options,
        index=default_index,
        key=f"{key_prefix}_user_select",
    )
    selected_user = users[options.index(selected_label)]
    manual_user = st.text_input(
        "Or enter User ID manually",
        value=selected_user.get("user_id", default_user_id),
        key=f"{key_prefix}_manual_user",
    )
    if manual_user and manual_user != selected_user.get("user_id"):
        return manual_user, None
    return selected_user.get("user_id", default_user_id), selected_user


def render_user_summary(user: dict[str, Any] | None, user_id: str) -> None:
    if not user:
        st.caption(f"Selected user ID: {user_id}")
        return
    col_name, col_id, col_sector, col_risk = st.columns(4)
    col_name.metric("User name", user.get("display_name", "Unknown"))
    col_id.metric("User ID", user.get("user_id", user_id))
    col_sector.metric("Sector", user.get("sector", "Unknown"))
    col_risk.metric("Risk", user.get("risk_profile", "Unknown"))
    st.caption(user.get("investment_goal", ""))


def fetch_quotes(tickers: list[str]) -> list[dict[str, Any]]:
    if not tickers:
        return []
    response = requests.get(
        f"{API_BASE_URL}/stock/quotes",
        params=[("tickers", ticker) for ticker in tickers],
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("quotes", [])


def render_quote_table(quotes: list[dict[str, Any]], title: str) -> None:
    st.markdown(f"### {title}")
    if not quotes:
        st.info("No stock quote data returned yet.")
        return
    df = pd.DataFrame(quotes)
    display_cols = [
        col
        for col in [
            "ticker",
            "company_name",
            "price",
            "previous_close",
            "currency",
            "market_cap",
            "sector",
            "industry",
        ]
        if col in df.columns
    ]
    if "price" in df.columns and "previous_close" in df.columns:
        df["daily_change_pct"] = (
            (pd.to_numeric(df["price"], errors="coerce") - pd.to_numeric(df["previous_close"], errors="coerce"))
            / pd.to_numeric(df["previous_close"], errors="coerce")
            * 100
        )
        display_cols.append("daily_change_pct")
    st.dataframe(df[display_cols], width="stretch", hide_index=True)
    if {"ticker", "price"}.issubset(df.columns):
        price_chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("ticker:N", title="Ticker"),
                y=alt.Y("price:Q", title="Live price", scale=alt.Scale(zero=False)),
                color=alt.Color("sector:N", title="Sector") if "sector" in df.columns else alt.value("#ff4b4b"),
                tooltip=display_cols,
            )
            .properties(height=330)
        )
        st.altair_chart(price_chart, width="stretch")


def build_portfolio_recommendations(
    portfolio_data: dict[str, Any],
    selected_user: dict[str, Any] | None,
) -> list[dict[str, str]]:
    holdings = portfolio_data.get("holdings") or []
    if not holdings:
        return [
            {
                "priority": "info",
                "recommendation": "Run portfolio analysis to generate recommendations.",
                "reason": "No structured holdings were returned yet.",
            }
        ]

    total_value = float(portfolio_data.get("total_value") or 0)
    rows = []
    for holding in holdings:
        market_value = float(holding.get("market_value") or 0)
        allocation = (market_value / total_value * 100) if total_value else 0
        rows.append({**holding, "allocation_percent": allocation})

    recommendations: list[dict[str, str]] = []
    concentrated = sorted(rows, key=lambda row: row["allocation_percent"], reverse=True)[:3]
    if concentrated and concentrated[0]["allocation_percent"] >= 30:
        recommendations.append(
            {
                "priority": "High",
                "recommendation": f"Review concentration in {concentrated[0]['ticker']}.",
                "reason": f"{concentrated[0]['ticker']} is {concentrated[0]['allocation_percent']:.1f}% of the portfolio, which increases single-stock risk.",
            }
        )

    losers = sorted(rows, key=lambda row: float(row.get("gain_loss") or 0))[:3]
    if losers and float(losers[0].get("gain_loss") or 0) < 0:
        recommendations.append(
            {
                "priority": "Medium",
                "recommendation": f"Review loss-making position {losers[0]['ticker']} before adding more.",
                "reason": f"{losers[0]['ticker']} has current unrealized loss of ${float(losers[0].get('gain_loss') or 0):,.2f}.",
            }
        )

    risk_profile = (selected_user or {}).get("risk_profile", "balanced")
    sector = (selected_user or {}).get("sector", "diversified sectors")
    recommendations.append(
        {
            "priority": "Strategy",
            "recommendation": f"Align new ideas with the user's {risk_profile} profile and {sector} interest.",
            "reason": "Recommendations should match the selected user's investment goal instead of using one default portfolio.",
        }
    )

    recommendations.append(
        {
            "priority": "Diversify",
            "recommendation": "Compare at least 2-3 sectors before investing new capital.",
            "reason": "This reduces dependence on a single market theme and improves risk balance.",
        }
    )
    return recommendations


def render_sidebar() -> str:
    with st.sidebar:
        st.header("Stock Chatbot")
        session_id = st.text_input("Chat / User ID", value="demo-user", key="chat_session")
        st.caption("Ask questions here. Past messages are saved and reused as context.")

        if st.button("Clear chat", key="clear_chat_button", width="stretch"):
            try:
                api_delete(f"/chat/{session_id}")
                st.session_state["chatbot_result"] = None
                st.session_state["last_agent_call"] = "None"
                st.session_state["last_agent_flow"] = None
                st.success("Chat cleared")
                st.rerun()
            except Exception as exc:
                st.error(f"Clear failed: {exc}")

        try:
            messages = api_get(f"/chat/{session_id}", limit=50).get("messages", [])
        except Exception:
            messages = []
        metric_col, agent_col = st.columns(2)
        metric_col.metric("Messages", len(messages))
        agent_col.metric("Last agent", st.session_state.get("last_agent_call", "None"))

        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)
        prompt = st.text_area(
            "Chat question",
            placeholder="Example: compare Apple and Meta, or analyze my portfolio",
            key="sidebar_prompt",
            height=95,
        )
        if st.button("Send", key="sidebar_send_button", type="primary", width="stretch"):
            if not prompt.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Calling supervisor agent..."):
                    try:
                        result = api_post("/research", {"question": prompt, "user_id": session_id})
                        st.session_state["chatbot_result"] = result
                        st.session_state["last_agent_call"] = result.get("agent", "Agent")
                        st.session_state["last_agent_flow"] = get_agent_flow(result)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Chat request failed: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.get("chatbot_result"):
            with st.expander("Latest chatbot answer", expanded=True):
                render_compact_agent_result(st.session_state["chatbot_result"])
            with st.expander("Supervisor and sub-agent call", expanded=True):
                render_agent_flow(st.session_state["chatbot_result"], title="Flow for latest chat")

        st.markdown("### Recent chat")
        render_chat_history(session_id, limit=4)

        with st.expander("Full chat history", expanded=False):
            render_chat_history(session_id, limit=30)

        with st.expander("Backend", expanded=False):
            st.code(API_BASE_URL)
            if st.button("Health check", key="sidebar_health_button", width="stretch"):
                try:
                    st.success(api_get("/health"))
                except Exception as exc:
                    st.error(f"API is not reachable: {exc}")

    return session_id


def render_research_tab(session_id: str) -> None:
    st.markdown("### Ask the Stock Agent")
    st.caption(
        "Ask for prices, comparisons, 5-year performance, profit/loss scenarios, "
        "or uploaded report analysis."
    )
    uploaded_file = st.file_uploader(
        "Upload a PDF or text financial report",
        type=["pdf", "txt", "md"],
        key="research_upload",
    )
    question = st.text_area(
        "Question",
        value="amazon stock 5 years report",
        height=120,
        key="research_question",
    )
    if st.button("Run research", key="run_research_button", type="primary"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Running supervisor agent..."):
                try:
                    if uploaded_file is not None:
                        files = {
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type,
                            )
                        }
                        data = {"question": question, "user_id": session_id}
                        response = requests.post(
                            f"{API_BASE_URL}/research/upload",
                            data=data,
                            files=files,
                            timeout=180,
                        )
                        response.raise_for_status()
                        result = response.json()
                    else:
                        result = api_post(
                            "/research",
                            {"question": question, "user_id": session_id},
                        )
                    st.session_state["research_result"] = result
                    st.session_state["last_agent_call"] = result.get("agent", "Agent")
                    st.session_state["last_agent_flow"] = get_agent_flow(result)
                except Exception as exc:
                    st.error(f"Research failed: {exc}")

    render_agent_result(st.session_state.get("research_result"))
    if st.session_state.get("research_result"):
        with st.expander("Supervisor and sub-agent call for this request", expanded=True):
            render_agent_flow(
                st.session_state.get("research_result"),
                title="Flow for this question/upload",
            )


def render_portfolio_tab(session_id: str) -> None:
    st.markdown("### Portfolio dashboard")
    st.caption("Review user holdings, risk concentration, gain/loss, and educational recommendations.")
    portfolio_user, selected_user = render_user_picker(session_id, "portfolio")
    render_user_summary(selected_user, portfolio_user)

    action_col, note_col = st.columns([1, 3])
    with action_col:
        analyze_clicked = st.button(
            "Analyze portfolio",
            key="analyze_portfolio_button",
            type="primary",
            width="stretch",
        )
    with note_col:
        st.info("This analysis is educational context only. It is not a buy/sell instruction.")

    if analyze_clicked:
        with st.spinner("Analyzing portfolio..."):
            try:
                result = api_post(
                    "/portfolio/analyze",
                    {"user_id": portfolio_user, "question": "analyze my portfolio"},
                )
                st.session_state["portfolio_result"] = result
                st.session_state["last_agent_call"] = result.get("agent", "Portfolio Agent")
            except Exception as exc:
                st.error(f"Portfolio API failed: {exc}")

    result = st.session_state.get("portfolio_result")
    holdings = (result or {}).get("data", {}).get("holdings", [])
    portfolio_data = (result or {}).get("data", {})
    if portfolio_data:
        st.markdown("### Portfolio health")
        total_value = float(portfolio_data.get("total_value") or 0)
        total_gain = float(portfolio_data.get("total_gain_loss") or 0)
        total_gain_pct = float(portfolio_data.get("total_gain_loss_percent") or 0)
        alert_count = len(portfolio_data.get("risk_alert_details") or [])
        col_value, col_gain, col_gain_pct, col_alerts = st.columns(4)
        col_value.metric("Portfolio value", f"${total_value:,.2f}")
        col_gain.metric("Total gain / loss", f"${total_gain:,.2f}", delta=f"{total_gain_pct:+.2f}%")
        col_gain_pct.metric("Return", f"{total_gain_pct:.2f}%")
        col_alerts.metric("Risk alerts", alert_count)

        with st.expander("Portfolio narrative", expanded=False):
            st.markdown((result or {}).get("answer", portfolio_data.get("answer", "")))

    if holdings:
        df = pd.DataFrame(holdings)
        df["allocation_percent"] = (
            pd.to_numeric(df["market_value"], errors="coerce")
            / max(float(portfolio_data.get("total_value") or 0), 1)
            * 100
        )
        top_row = df.sort_values("allocation_percent", ascending=False).iloc[0]
        worst_row = df.sort_values("gain_loss", ascending=True).iloc[0]

        highlight_col1, highlight_col2, highlight_col3 = st.columns(3)
        highlight_col1.metric(
            "Largest holding",
            str(top_row["ticker"]),
            f"{float(top_row['allocation_percent']):.1f}% allocation",
        )
        highlight_col2.metric(
            "Biggest loss",
            str(worst_row["ticker"]),
            f"${float(worst_row['gain_loss']):,.2f}",
        )
        highlight_col3.metric("Holdings", len(df))

        if {"ticker", "market_value"}.issubset(df.columns):
            pie_chart = (
                alt.Chart(df)
                .mark_arc()
                .encode(
                    theta=alt.Theta("market_value:Q"),
                    color=alt.Color("ticker:N"),
                    tooltip=["ticker", "market_value", "gain_loss"],
                )
                .properties(height=350)
            )
            bar_chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=alt.X("ticker:N", title="Ticker"),
                    y=alt.Y("gain_loss:Q", title="Gain / loss"),
                    color=alt.condition("datum.gain_loss >= 0", alt.value("#12b76a"), alt.value("#f04438")),
                    tooltip=["ticker", "quantity", "average_buy_price", "current_price", "market_value", "gain_loss"],
                )
                .properties(height=320)
            )
            exposure_chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=alt.X("allocation_percent:Q", title="Allocation %"),
                    y=alt.Y("ticker:N", sort="-x", title="Ticker"),
                    color=alt.condition("datum.allocation_percent >= 30", alt.value("#f04438"), alt.value("#2e90fa")),
                    tooltip=["ticker", "allocation_percent", "market_value"],
                )
                .properties(height=320)
            )

            chart_col, gain_col = st.columns(2)
            with chart_col:
                st.markdown("### Allocation")
                st.altair_chart(pie_chart, width="stretch")
            with gain_col:
                st.markdown("### Profit / loss")
                st.altair_chart(bar_chart, width="stretch")

            st.markdown("### Concentration risk")
            st.altair_chart(exposure_chart, width="stretch")

        st.markdown("### Holdings detail")
        display_cols = [
            "ticker",
            "quantity",
            "average_buy_price",
            "current_price",
            "market_value",
            "allocation_percent",
            "gain_loss",
        ]
        st.dataframe(df[[col for col in display_cols if col in df.columns]], width="stretch", hide_index=True)

    risk_details = portfolio_data.get("risk_alert_details") or []
    if risk_details:
        st.markdown("### Risk alerts")
        risk_df = pd.DataFrame(risk_details)
        st.dataframe(risk_df, width="stretch", hide_index=True)
        risk_counts = risk_df.groupby("severity").size().reset_index(name="alerts")
        risk_chart = (
            alt.Chart(risk_counts)
            .mark_bar()
            .encode(
                x=alt.X("severity:N", title="Severity"),
                y=alt.Y("alerts:Q", title="Alert count"),
                color=alt.Color("severity:N", legend=None),
                tooltip=["severity", "alerts"],
            )
            .properties(height=260)
        )
        st.altair_chart(risk_chart, width="stretch")

    if portfolio_data:
        st.markdown("### Recommendations")
        recs = build_portfolio_recommendations(portfolio_data, selected_user)
        for rec in recs:
            with st.container(border=True):
                st.markdown(f"**{rec['priority']} - {rec['recommendation']}**")
                st.caption(rec["reason"])
        render_disclaimer()


def render_watchlist_tab(session_id: str) -> None:
    st.markdown("### My Watchlist")
    watchlist_user, selected_user = render_user_picker(session_id, "watchlist")
    render_user_summary(selected_user, watchlist_user)

    if st.button("Show selected user's watchlist", key="show_watchlist_button", type="primary", width="stretch"):
        try:
            st.session_state["watchlist_result"] = api_get(f"/watchlist/{watchlist_user}")
        except Exception as exc:
            st.error(f"Watchlist API failed: {exc}")

    watchlist_result = st.session_state.get("watchlist_result")
    if watchlist_result:
        st.markdown("### User interested stocks")
        tickers = watchlist_result.get("watchlist", [])
        if tickers:
            ticker_df = pd.DataFrame(
                [{"position": index + 1, "ticker": ticker} for index, ticker in enumerate(tickers)]
            )
            st.dataframe(ticker_df, width="stretch", hide_index=True)
            refresh_watchlist_quotes = st.button(
                "Refresh selected user's live stock prices",
                key="refresh_user_watchlist_quotes",
                width="stretch",
            )
            watchlist_quotes_key = f"watchlist_quotes_{watchlist_user}"
            if refresh_watchlist_quotes or watchlist_quotes_key not in st.session_state:
                with st.spinner("Fetching live prices for interested stocks..."):
                    try:
                        st.session_state[watchlist_quotes_key] = fetch_quotes(tickers)
                    except Exception as exc:
                        st.error(f"Live watchlist quote fetch failed: {exc}")
                        st.session_state[watchlist_quotes_key] = []
            render_quote_table(st.session_state.get(watchlist_quotes_key, []), "Live prices for interested stocks")
        st.caption(watchlist_result.get("answer", ""))

    st.markdown("### Live Top 10 stocks")
    refresh_top10 = st.button("Refresh live Top 10 stocks", key="refresh_top10_quotes", type="primary")
    if refresh_top10 or "top10_quotes" not in st.session_state:
        with st.spinner("Fetching live Top 10 stocks..."):
            try:
                top10 = api_get("/stock/top10")
                st.session_state["top10_quotes"] = top10.get("quotes", [])
            except Exception as exc:
                st.error(f"Top 10 refresh failed: {exc}")
                st.session_state["top10_quotes"] = []
    render_quote_table(st.session_state.get("top10_quotes", []), "Top 10 live stock prices")

    render_disclaimer()


def render_observability_tab() -> None:
    st.markdown("### Observability")
    if st.button("Refresh observability summary", key="refresh_observability_button", type="primary"):
        try:
            st.session_state["observability_result"] = api_get("/observability/summary")
        except Exception as exc:
            st.error(f"Observability API failed: {exc}")
    if not st.session_state.get("observability_result"):
        try:
            st.session_state["observability_result"] = api_get("/observability/summary")
        except Exception:
            st.session_state["observability_result"] = {}
    summary = st.session_state.get("observability_result", {})

    col_req, col_err, col_lat, col_cost = st.columns(4)
    col_req.metric("Requests", summary.get("request_count", 0))
    col_err.metric("Error rate", f"{summary.get('error_rate', 0) * 100:.2f}%")
    col_lat.metric("Avg latency", f"{summary.get('avg_latency_ms', 0):.0f} ms")
    col_cost.metric("LLM cost", f"${summary.get('total_cost_usd', 0):.6f}")

    col_tokens, col_llm, col_p50, col_p95 = st.columns(4)
    col_tokens.metric("Tokens", summary.get("total_tokens", 0))
    col_llm.metric("LLM calls", summary.get("llm_call_count", 0))
    col_p50.metric("P50 latency", f"{summary.get('p50_latency_ms', 0):.0f} ms")
    col_p95.metric("P95 latency", f"{summary.get('p95_latency_ms', 0):.0f} ms")

    events = summary.get("events", [])
    if events:
        events_df = pd.DataFrame(events)
        st.markdown("### Recent events")
        visible_cols = [
            col
            for col in [
                "timestamp",
                "event_type",
                "agent",
                "route",
                "question",
                "model_id",
                "latency_ms",
                "total_tokens",
                "cost_usd",
                "success",
                "error",
            ]
            if col in events_df.columns
        ]
        st.dataframe(events_df[visible_cols].tail(100), width="stretch", hide_index=True)

        request_df = events_df[events_df.get("event_type") == "request"] if "event_type" in events_df else pd.DataFrame()
        if not request_df.empty and {"agent", "latency_ms"}.issubset(request_df.columns):
            latency_chart = (
                alt.Chart(request_df)
                .mark_bar()
                .encode(
                    x=alt.X("agent:N", title="Agent"),
                    y=alt.Y("mean(latency_ms):Q", title="Average latency ms"),
                    tooltip=["agent", "mean(latency_ms)"],
                )
                .properties(height=300)
            )
            st.markdown("### Average latency by agent")
            st.altair_chart(latency_chart, width="stretch")

        ragas_rows: list[dict[str, Any]] = []
        for event in events:
            metadata = event.get("metadata") or {}
            ragas = metadata.get("ragas") or event.get("ragas")
            if isinstance(ragas, dict):
                for score in ragas.get("scores", []):
                    ragas_rows.append(
                        {
                            "timestamp": event.get("timestamp"),
                            "question": event.get("question"),
                            "score": score.get("name"),
                            "value": score.get("value"),
                            "passed": ragas.get("passed"),
                            "comment": score.get("comment"),
                        }
                    )
        for result_key in ["research_result", "chatbot_result"]:
            result = st.session_state.get(result_key) or {}
            ragas = (result.get("data") or {}).get("ragas")
            if isinstance(ragas, dict):
                for score in ragas.get("scores", []):
                    ragas_rows.append(
                        {
                            "timestamp": "current session",
                            "question": result.get("answer", "")[:80],
                            "score": score.get("name"),
                            "value": score.get("value"),
                            "passed": ragas.get("passed"),
                            "comment": score.get("comment"),
                        }
                    )
        st.markdown("### RAGAS evaluation")
        if ragas_rows:
            ragas_df = pd.DataFrame(ragas_rows)
            st.dataframe(ragas_df.tail(50), width="stretch", hide_index=True)
            ragas_chart = (
                alt.Chart(ragas_df)
                .mark_bar()
                .encode(
                    x=alt.X("score:N", title="RAGAS metric"),
                    y=alt.Y("mean(value):Q", title="Average score", scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color("score:N", legend=None),
                    tooltip=["score", "mean(value)"],
                )
                .properties(height=300)
            )
            st.altair_chart(ragas_chart, width="stretch")
        else:
            st.warning(
                "No RAGAS scores found yet. RAGAS is generated only for RAG/report questions. "
                "Go to Agent Research, upload a PDF/TXT/MD report or ask for a stored financial report, "
                "then refresh this Observability tab."
            )

    with st.expander("Raw observability JSON", expanded=False):
        st.json(summary)


def render_settings_tab() -> None:
    st.markdown("### Runtime settings")
    try:
        st.json(api_get("/config"))
    except Exception as exc:
        st.error(f"Settings API failed: {exc}")


st.set_page_config(page_title="Stock Market Agent", layout="wide")
init_state()
apply_styles()

session_id = render_sidebar()

st.markdown(
    """
    <div class="hero-card">
        <h3>Stock Market Agent</h3>
        <p>Research stocks, review portfolio risk, analyze reports, and keep chat history in one clean dashboard.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_research, tab_portfolio, tab_watchlist, tab_observability, tab_settings = st.tabs(
    ["Agent Research", "My Portfolio", "My Watchlist", "Observability", "Settings"]
)

with tab_research:
    render_research_tab(session_id)

with tab_portfolio:
    render_portfolio_tab(session_id)

with tab_watchlist:
    render_watchlist_tab(session_id)

with tab_observability:
    render_observability_tab()

with tab_settings:
    render_settings_tab()
