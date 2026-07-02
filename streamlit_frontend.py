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
        "chatbot_result": None,
        "last_agent_call": "None",
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
    st.altair_chart(chart, use_container_width=True)
    with st.expander("Monthly history table", expanded=False):
        table = df.copy()
        table["month"] = table["month"].dt.strftime("%Y-%m")
        st.dataframe(table, use_container_width=True, hide_index=True)


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


def render_sidebar() -> str:
    with st.sidebar:
        st.header("Stock Chatbot")
        session_id = st.text_input("Chat / User ID", value="demo-user", key="chat_session")
        st.caption("Past messages are saved and reused as context.")

        col_clear, col_refresh = st.columns(2)
        with col_clear:
            if st.button("Clear", key="clear_chat_button", use_container_width=True):
                try:
                    api_delete(f"/chat/{session_id}")
                    st.session_state["chatbot_result"] = None
                    st.success("Cleared")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Clear failed: {exc}")
        with col_refresh:
            if st.button("Refresh", key="refresh_chat_button", use_container_width=True):
                st.rerun()

        try:
            messages = api_get(f"/chat/{session_id}", limit=50).get("messages", [])
        except Exception:
            messages = []
        metric_col, agent_col = st.columns(2)
        metric_col.metric("Messages", len(messages))
        agent_col.metric("Last agent", st.session_state.get("last_agent_call", "None"))

        prompt = st.text_area(
            "Ask the assistant",
            placeholder="Example: compare Apple and Meta, or analyze my portfolio",
            key="sidebar_prompt",
            height=95,
        )
        if st.button("Send", key="sidebar_send_button", type="primary", use_container_width=True):
            if not prompt.strip():
                st.warning("Please enter a question.")
            else:
                with st.spinner("Calling supervisor agent..."):
                    try:
                        result = api_post("/research", {"question": prompt, "user_id": session_id})
                        st.session_state["chatbot_result"] = result
                        st.session_state["last_agent_call"] = result.get("agent", "Agent")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Chat request failed: {exc}")

        st.markdown("### Recent chat")
        render_chat_history(session_id, limit=4)

        with st.expander("Full chat history", expanded=False):
            render_chat_history(session_id, limit=30)

        with st.expander("Backend", expanded=False):
            st.code(API_BASE_URL)
            if st.button("Health check", key="sidebar_health_button", use_container_width=True):
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
                except Exception as exc:
                    st.error(f"Research failed: {exc}")

    render_agent_result(st.session_state.get("research_result"))


def render_portfolio_tab(session_id: str) -> None:
    st.markdown("### Portfolio dashboard")
    portfolio_user = st.text_input("Portfolio user ID", value=session_id, key="portfolio_user")
    if st.button("Analyze portfolio", key="analyze_portfolio_button"):
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
    render_agent_result(result)
    holdings = (result or {}).get("data", {}).get("holdings", [])
    if holdings:
        df = pd.DataFrame(holdings)
        st.markdown("### Holdings")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if {"ticker", "market_value"}.issubset(df.columns):
            pie = (
                alt.Chart(df)
                .mark_arc()
                .encode(
                    theta=alt.Theta("market_value:Q"),
                    color=alt.Color("ticker:N"),
                    tooltip=["ticker", "market_value", "gain_loss"],
                )
                .properties(height=350)
            )
            st.altair_chart(pie, use_container_width=True)


def render_watchlist_tab(session_id: str) -> None:
    st.markdown("### My Watchlist")
    col_watch, col_users = st.columns(2)
    with col_watch:
        if st.button("Show my saved watchlist", key="show_watchlist_button", use_container_width=True):
            try:
                st.session_state["watchlist_result"] = api_get(f"/watchlist/{session_id}")
            except Exception as exc:
                st.error(f"Watchlist API failed: {exc}")
    with col_users:
        if st.button("List seeded users", key="list_users_button", use_container_width=True):
            try:
                st.session_state["users_result"] = api_get("/users")
            except Exception as exc:
                st.error(f"Users API failed: {exc}")

    if st.session_state.get("watchlist_result"):
        st.json(st.session_state["watchlist_result"])

    users = (st.session_state.get("users_result") or {}).get("users", [])
    if users:
        st.markdown("### Seeded users")
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
    render_disclaimer()


def render_observability_tab() -> None:
    st.markdown("### Observability")
    if st.button("Refresh observability summary", key="refresh_observability_button"):
        try:
            st.session_state["observability_result"] = api_get("/observability/summary")
        except Exception as exc:
            st.error(f"Observability API failed: {exc}")
    if "observability_result" not in st.session_state:
        try:
            st.session_state["observability_result"] = api_get("/observability/summary")
        except Exception:
            st.session_state["observability_result"] = {}
    st.json(st.session_state.get("observability_result", {}))


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

if st.session_state.get("chatbot_result"):
    with st.expander("Latest chatbot answer", expanded=False):
        render_agent_result(st.session_state["chatbot_result"])

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
