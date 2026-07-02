from __future__ import annotations

import os
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8002").rstrip("/")
DISCLAIMER = (
    "Educational stock research only. This is not financial, investment, legal, "
    "or tax advice. Verify data before making decisions."
)


def api_get(path: str, **params: Any) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def api_delete(path: str) -> dict[str, Any]:
    response = requests.delete(f"{API_BASE_URL}{path}", timeout=60)
    response.raise_for_status()
    return response.json()


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
            tooltip=["ticker", alt.Tooltip("month:T", format="%Y-%m"), "open", "high", "low", "close", "volume"],
        )
        .properties(height=360)
    )
    st.markdown("### 5-year monthly close chart")
    st.altair_chart(chart, width="stretch")
    with st.expander("Monthly history table"):
        table = df.copy()
        table["month"] = table["month"].dt.strftime("%Y-%m")
        st.dataframe(table, width="stretch", hide_index=True)


def render_answer(result: dict[str, Any]) -> None:
    st.subheader(result.get("agent", "Agent"))
    st.write(result.get("answer", "No answer returned."))
    render_stock_history_chart(result)
    if result.get("sources"):
        with st.expander("Sources"):
            st.write(result["sources"])
    st.info(DISCLAIMER)


st.set_page_config(page_title="Stock Market Agent", layout="wide")
st.title("Stock Market Agent")
st.caption("Streamlit frontend calling a separate FastAPI backend.")

with st.sidebar:
    st.header("Backend")
    st.code(API_BASE_URL)
    session_id = st.text_input("User / session ID", value="demo-user")
    if st.button("Health check"):
        try:
            st.success(api_get("/health"))
        except Exception as exc:
            st.error(f"API is not reachable: {exc}")
    if st.button("Clear chat"):
        api_delete(f"/chat/{session_id}")
        st.success("Chat cleared")

research_tab, portfolio_tab, watchlist_tab, chat_tab, settings_tab = st.tabs(
    ["Agent Research", "Portfolio", "Watchlist", "Chat History", "Settings"]
)

with research_tab:
    st.markdown("### Ask the agent")
    question = st.text_area("Question", value="amazon stock 5 years report", height=120)
    uploaded_file = st.file_uploader("Optional PDF/TXT/MD financial report", type=["pdf", "txt", "md"])
    if st.button("Run research", type="primary"):
        try:
            if uploaded_file is not None:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
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
                result = api_post("/research", {"question": question, "user_id": session_id})
            render_answer(result)
        except Exception as exc:
            st.error(f"Research failed: {exc}")

with portfolio_tab:
    st.markdown("### Portfolio analysis")
    portfolio_user = st.text_input("Portfolio user ID", value=session_id)
    if st.button("Analyze portfolio"):
        try:
            result = api_post(
                "/portfolio/analyze",
                {"user_id": portfolio_user, "question": "analyze my portfolio"},
            )
            render_answer(result)
            holdings = (result.get("data") or {}).get("holdings", [])
            if holdings:
                df = pd.DataFrame(holdings)
                st.dataframe(df, width="stretch", hide_index=True)
                if "market_value" in df.columns:
                    st.bar_chart(df.set_index("ticker")["market_value"], width="stretch")
        except Exception as exc:
            st.error(f"Portfolio API failed: {exc}")

with watchlist_tab:
    st.markdown("### Watchlist")
    if st.button("Show my watchlist"):
        try:
            result = api_get(f"/watchlist/{session_id}")
            st.write(result)
        except Exception as exc:
            st.error(f"Watchlist API failed: {exc}")
    if st.button("List seeded users"):
        try:
            result = api_get("/users")
            users = result.get("users", [])
            st.dataframe(pd.DataFrame(users), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Users API failed: {exc}")

with chat_tab:
    st.markdown("### Chat history")
    try:
        history = api_get(f"/chat/{session_id}", limit=50)
        for message in history.get("messages", []):
            role = "user" if message.get("role") == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(message.get("content", ""))
                st.caption(message.get("created_at", ""))
    except Exception as exc:
        st.error(f"Chat history failed: {exc}")

with settings_tab:
    st.markdown("### Runtime config")
    try:
        st.json(api_get("/config"))
        st.markdown("### Observability summary")
        st.json(api_get("/observability/summary"))
    except Exception as exc:
        st.error(f"Settings API failed: {exc}")