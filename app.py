from datetime import datetime
from typing import Any

import altair as alt
import streamlit as st
import pandas as pd

from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.graphs.langgraph_supervisor import LangGraphSupervisor
from stock_market_agent.config import get_settings
from stock_market_agent.services.chat_history import ChatHistoryService
from stock_market_agent.services.mcp_client import McpClient


TOP_10_STOCKS = ["AAPL", "MSFT", "NVDA", "META", "AMZN", "GOOGL", "AVGO", "TSLA", "COST", "NFLX"]
STOCK_ADVICE_DISCLAIMER = (
    "Disclaimer: This app is for educational stock research only. "
    "It is not financial, investment, legal, or tax advice. "
    "Please verify data and consult a licensed financial advisor before making investment decisions."
)


def format_market_cap(value: float | int | None) -> str:
    if value is None:
        return "Not available"
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def fetch_live_quotes(client: McpClient, tickers: list[str]) -> list[dict]:
    rows: list[dict] = []
    for ticker in tickers:
        result = client.call_tool("get_stock_quote", {"ticker_or_company": ticker})
        quote = result.get("quote", {})
        rows.append(
            {
                "Ticker": quote.get("ticker", ticker),
                "Company": quote.get("company_name") or "Not available",
                "Price": quote.get("price"),
                "Previous Close": quote.get("previous_close"),
                "Currency": quote.get("currency") or "USD",
                "Market Cap": format_market_cap(quote.get("market_cap")),
                "Sector": quote.get("sector") or "Not available",
                "Industry": quote.get("industry") or "Not available",
            }
        )
    return rows


def fetch_live_top_10_quotes(client: McpClient) -> list[dict]:
    return fetch_live_quotes(client, TOP_10_STOCKS)


def fetch_investment_users(client: McpClient) -> list[dict]:
    try:
        result = client.call_tool("list_investment_users", {})
    except Exception:
        return []
    return result.get("users", [])


def user_option_label(user_id: str, users: list[dict]) -> str:
    if user_id == "demo-user":
        return "Demo User — demo-user"
    user = next((item for item in users if item["user_id"] == user_id), None)
    if not user:
        return user_id
    return (
        f"{user.get('display_name', user_id)} — {user_id} "
        f"({user.get('sector', 'sector not set')})"
    )


def show_stock_advice_disclaimer() -> None:
    st.info(STOCK_ADVICE_DISCLAIMER)


def render_allocation_pie(chart_df: pd.DataFrame) -> None:
    pie_df = chart_df[chart_df["market_value"] > 0].copy()
    if pie_df.empty:
        st.info("Allocation pie chart is unavailable because market values are missing.")
        return

    pie_df["label"] = pie_df.apply(
        lambda row: f"{row['ticker']} ({row['allocation_percent']:.1f}%)",
        axis=1,
    )
    chart = (
        alt.Chart(pie_df)
        .mark_arc(innerRadius=55, outerRadius=120)
        .encode(
            theta=alt.Theta("market_value:Q", title="Market value"),
            color=alt.Color("ticker:N", title="Ticker"),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("market_value:Q", title="Market value", format="$,.2f"),
                alt.Tooltip("allocation_percent:Q", title="Allocation %", format=".2f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")


def render_gain_loss_chart(chart_df: pd.DataFrame) -> None:
    chart = (
        alt.Chart(chart_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("ticker:N", title="Ticker", sort=None),
            y=alt.Y("gain_loss:Q", title="Gain / loss"),
            color=alt.condition(
                alt.datum.gain_loss >= 0,
                alt.value("#16a34a"),
                alt.value("#dc2626"),
            ),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("gain_loss:Q", title="Gain / loss", format="$,.2f"),
                alt.Tooltip("market_value:Q", title="Market value", format="$,.2f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")


def render_risk_alert_chart(data: dict) -> None:
    risk_alert_details = data.get("risk_alert_details", [])
    if not risk_alert_details:
        st.info("Risk alert chart is unavailable because no structured risk details were returned.")
        return

    severity_order = ["high", "medium", "low", "info"]
    severity_labels = {
        "high": "High",
        "medium": "Medium",
        "low": "Low / OK",
        "info": "Info",
    }
    severity_colors = {
        "High": "#dc2626",
        "Medium": "#f59e0b",
        "Low / OK": "#16a34a",
        "Info": "#2563eb",
    }
    risk_counts = []
    for severity in severity_order:
        count = sum(1 for alert in risk_alert_details if alert.get("severity") == severity)
        if count:
            risk_counts.append({"severity": severity_labels[severity], "count": count})

    if not risk_counts:
        st.info("No risk severity counts are available.")
        return

    risk_df = pd.DataFrame(risk_counts)
    pie_chart = (
        alt.Chart(risk_df)
        .mark_arc(innerRadius=50, outerRadius=110)
        .encode(
            theta=alt.Theta("count:Q", title="Alert count"),
            color=alt.Color(
                "severity:N",
                title="Severity",
                scale=alt.Scale(
                    domain=list(severity_colors.keys()),
                    range=list(severity_colors.values()),
                ),
            ),
            tooltip=[
                alt.Tooltip("severity:N", title="Severity"),
                alt.Tooltip("count:Q", title="Alerts"),
            ],
        )
        .properties(height=280)
    )
    bar_chart = (
        alt.Chart(risk_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("severity:N", title="Severity", sort=list(severity_colors.keys())),
            y=alt.Y("count:Q", title="Alert count"),
            color=alt.Color(
                "severity:N",
                legend=None,
                scale=alt.Scale(
                    domain=list(severity_colors.keys()),
                    range=list(severity_colors.values()),
                ),
            ),
            tooltip=[
                alt.Tooltip("severity:N", title="Severity"),
                alt.Tooltip("count:Q", title="Alerts"),
            ],
        )
        .properties(height=280)
    )
    risk_pie_col, risk_bar_col = st.columns(2)
    with risk_pie_col:
        st.caption("Risk severity mix")
        st.altair_chart(pie_chart, width="stretch")
    with risk_bar_col:
        st.caption("Risk alert counts")
        st.altair_chart(bar_chart, width="stretch")


def show_portfolio_risk_alerts(data: dict) -> None:
    risk_alert_details = data.get("risk_alert_details", [])
    risk_alerts = data.get("risk_alerts", [])

    if risk_alert_details:
        high_count = sum(1 for alert in risk_alert_details if alert.get("severity") == "high")
        medium_count = sum(1 for alert in risk_alert_details if alert.get("severity") == "medium")
        low_count = sum(1 for alert in risk_alert_details if alert.get("severity") == "low")

        risk_col_high, risk_col_medium, risk_col_low = st.columns(3)
        risk_col_high.metric("High risk", high_count)
        risk_col_medium.metric("Medium risk", medium_count)
        risk_col_low.metric("Low / ok", low_count)

        for alert in risk_alert_details:
            severity = alert.get("severity", "info")
            message = alert.get("message", "")
            if severity == "high":
                st.error(f"High: {message}")
            elif severity == "medium":
                st.warning(f"Medium: {message}")
            elif severity == "low":
                st.success(f"Low: {message}")
            else:
                st.info(message)
    elif risk_alerts:
        for alert in risk_alerts:
            if "No major" in alert:
                st.success(alert)
            else:
                st.warning(alert)
    else:
        st.info("No portfolio risk alerts returned.")

    with st.expander("How to read these risk alerts"):
        st.write(
            "High alerts usually mean single-stock concentration, large unrealized loss, "
            "or portfolio drawdown. Medium alerts usually mean diversification, sector "
            "concentration, missing data, or watch-level losses. These are screening signals, "
            "not automatic buy/sell instructions."
        )


def build_portfolio_recommendations(
    user_profile: dict | None,
    holdings: list[dict],
    quote_rows: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Rank user-specific stock and sector ideas from portfolio/watchlist context."""

    if not quote_rows:
        return pd.DataFrame(), pd.DataFrame(), []

    user_sector = (user_profile or {}).get("sector", "")
    risk_profile = ((user_profile or {}).get("risk_profile") or "balanced").lower()
    holdings_by_ticker = {str(item.get("ticker", "")).upper(): item for item in holdings}

    sector_counts: dict[str, int] = {}
    for row in quote_rows:
        sector = row.get("Sector") or "Not available"
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    stock_rows: list[dict[str, Any]] = []
    for row in quote_rows:
        ticker = str(row.get("Ticker", "")).upper()
        sector = row.get("Sector") or "Not available"
        price = row.get("Price")
        previous_close = row.get("Previous Close")
        holding = holdings_by_ticker.get(ticker, {})
        gain_loss = float(holding.get("gain_loss") or 0)
        market_value = float(holding.get("market_value") or 0)
        average_buy_price = float(holding.get("average_buy_price") or 0)
        gain_loss_percent = (
            (gain_loss / (market_value - gain_loss)) * 100
            if (market_value - gain_loss)
            else 0
        )
        momentum_percent = (
            ((float(price) - float(previous_close)) / float(previous_close)) * 100
            if price is not None and previous_close
            else 0
        )

        score = 50.0
        score += min(max(momentum_percent, -5), 5) * 2
        score += min(max(gain_loss_percent, -20), 20) * 0.35

        if user_sector and user_sector.lower() in sector.lower():
            score += 12
        if sector_counts.get(sector, 0) <= 2:
            score += 8
        if risk_profile in {"conservative", "moderate"} and momentum_percent < -2:
            score -= 8
        if risk_profile == "aggressive" and momentum_percent > 1:
            score += 5
        if average_buy_price and price and float(price) > average_buy_price:
            score += 4

        reason_parts = []
        if user_sector and user_sector.lower() in sector.lower():
            reason_parts.append("matches user sector preference")
        if sector_counts.get(sector, 0) <= 2:
            reason_parts.append("adds diversification")
        if momentum_percent > 0:
            reason_parts.append(f"positive recent price move {momentum_percent:+.2f}%")
        elif momentum_percent < 0:
            reason_parts.append(f"recent price pullback {momentum_percent:+.2f}%")
        if gain_loss_percent:
            reason_parts.append(f"portfolio gain/loss {gain_loss_percent:+.2f}%")

        stock_rows.append(
            {
                "Ticker": ticker,
                "Company": row.get("Company") or "Not available",
                "Sector": sector,
                "Price": price,
                "Recent move %": momentum_percent,
                "Portfolio gain/loss %": gain_loss_percent,
                "Fit score": round(score, 1),
                "Why it fits": "; ".join(reason_parts) or "use as a comparison candidate",
            }
        )

    stock_df = pd.DataFrame(stock_rows).sort_values(
        ["Fit score", "Recent move %"],
        ascending=[False, False],
    )

    sector_rows: list[dict[str, Any]] = []
    for sector in sorted(sector_counts):
        sector_stock_df = stock_df[stock_df["Sector"] == sector]
        average_score = float(sector_stock_df["Fit score"].mean()) if not sector_stock_df.empty else 0
        preference_boost = 10 if user_sector and user_sector.lower() in sector.lower() else 0
        diversification_boost = 8 if sector_counts[sector] <= 2 else 0
        sector_rows.append(
            {
                "Sector": sector,
                "Stocks tracked": sector_counts[sector],
                "Average fit score": round(average_score + preference_boost + diversification_boost, 1),
                "Best candidates": ", ".join(sector_stock_df.head(3)["Ticker"].tolist()),
            }
        )
    sector_df = pd.DataFrame(sector_rows).sort_values(
        "Average fit score",
        ascending=False,
    )

    guidance = [
        f"User risk profile: {risk_profile}. Recommendations are adjusted for this profile.",
        f"Preferred sector: {user_sector or 'not configured'}. Sector match receives a higher fit score.",
        "Diversification is rewarded so the user is not guided only into one concentrated sector.",
    ]
    return stock_df, sector_df, guidance


def render_portfolio_recommendations(
    user_profile: dict | None,
    holdings: list[dict],
    mcp_client: McpClient,
) -> None:
    st.markdown("### Recommendations for this user")
    st.caption(
        "Educational ranking based on the selected user's risk profile, preferred sector, "
        "current holdings, diversification, and live quote data."
    )

    candidate_tickers = list(
        dict.fromkeys(
            [
                *[str(item.get("ticker", "")).upper() for item in holdings],
                *((user_profile or {}).get("watchlist") or []),
            ]
        )
    )
    candidate_tickers = [ticker for ticker in candidate_tickers if ticker][:15]
    if not candidate_tickers:
        st.info("No holdings or watchlist stocks are available for recommendations.")
        return

    with st.spinner("Building user-specific stock and sector recommendations..."):
        quote_rows = fetch_live_quotes(mcp_client, candidate_tickers)
        stock_df, sector_df, guidance = build_portfolio_recommendations(
            user_profile,
            holdings,
            quote_rows,
        )

    if stock_df.empty:
        st.info("Recommendations are unavailable because live quote data was not returned.")
        return

    best_stock_col, best_sector_col = st.columns(2)
    top_stock = stock_df.iloc[0]
    top_sector = sector_df.iloc[0] if not sector_df.empty else None
    with best_stock_col:
        st.metric(
            "Best-fit stock idea",
            top_stock["Ticker"],
            f"Fit score {top_stock['Fit score']}",
        )
        st.caption(str(top_stock["Why it fits"]))
    with best_sector_col:
        if top_sector is not None:
            st.metric(
                "Best-fit sector idea",
                top_sector["Sector"],
                f"Score {top_sector['Average fit score']}",
            )
            st.caption(f"Candidates: {top_sector['Best candidates']}")

    st.markdown("#### Top stock ideas")
    st.dataframe(
        stock_df.head(5),
        width="stretch",
        column_config={
            "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
            "Recent move %": st.column_config.NumberColumn("Recent move %", format="%.2f%%"),
            "Portfolio gain/loss %": st.column_config.NumberColumn(
                "Portfolio gain/loss %",
                format="%.2f%%",
            ),
            "Fit score": st.column_config.NumberColumn("Fit score", format="%.1f"),
        },
    )

    st.markdown("#### Sector ideas")
    sector_chart = (
        alt.Chart(sector_df.head(6))
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Average fit score:Q", title="Fit score"),
            y=alt.Y("Sector:N", title="Sector", sort="-x"),
            color=alt.value("#2563eb"),
            tooltip=[
                alt.Tooltip("Sector:N", title="Sector"),
                alt.Tooltip("Average fit score:Q", title="Fit score"),
                alt.Tooltip("Best candidates:N", title="Best candidates"),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(sector_chart, width="stretch")
    st.dataframe(sector_df.head(6), width="stretch")

    with st.expander("How these recommendations are calculated"):
        for item in guidance:
            st.write(f"- {item}")
        st.write(
            "- Fit score combines sector preference, diversification, recent price move, "
            "and current portfolio gain/loss. It is a screening score, not a buy signal."
        )

    show_stock_advice_disclaimer()


def apply_app_styles() -> None:
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
        }
        html, body, [class*="css"] {
            font-size: 18px;
        }
        p, label, span, div, button, input, textarea {
            font-size: 1.03rem;
        }
        h1 {
            font-size: 3rem !important;
        }
        h2 {
            font-size: 2.15rem !important;
        }
        h3 {
            font-size: 1.55rem !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #101828 0%, #182230 100%);
        }
        [data-testid="stSidebar"] * {
            color: #f9fafb;
        }
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] input {
            background-color: #ffffff !important;
            color: #101828 !important;
        }
        [data-testid="stSidebar"] button {
            background-color: #ffffff !important;
            color: #101828 !important;
            border: 1px solid #d0d5dd !important;
            font-weight: 800 !important;
        }
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button span,
        [data-testid="stSidebar"] button div {
            color: #101828 !important;
            font-weight: 800 !important;
        }
        [data-testid="stSidebar"] [data-testid="stMetricValue"],
        [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
            color: #ffffff !important;
        }
        .hero-card {
            padding: 1.8rem 2rem;
            border-radius: 1.1rem;
            background: linear-gradient(135deg, #111827 0%, #243b6b 50%, #ef4444 140%);
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 12px 35px rgba(17, 24, 39, 0.18);
        }
        .hero-card h1 {
            margin: 0;
            font-size: 3rem;
            line-height: 1.1;
        }
        .hero-card p {
            margin: 0.6rem 0 0 0;
            color: #e5e7eb;
            font-size: 1.25rem;
        }
        .mini-card {
            padding: 0.9rem 1rem;
            border: 1px solid #eaecf0;
            border-radius: 0.9rem;
            background: #ffffff;
            box-shadow: 0 4px 14px rgba(16, 24, 40, 0.06);
        }
        .mini-card-title {
            font-size: 0.8rem;
            color: #667085;
            margin-bottom: 0.25rem;
        }
        .mini-card-value {
            font-size: 1.1rem;
            color: #101828;
            font-weight: 700;
        }
        div[data-testid="stTabs"] button {
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_status_cards() -> None:
    col_agents, col_mcp, col_aws = st.columns(3)
    with col_agents:
        st.markdown(
            """
            <div class="mini-card">
              <div class="mini-card-title">Agents</div>
              <div class="mini-card-value">Stock · RAG · User · Portfolio</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_mcp:
        st.markdown(
            """
            <div class="mini-card">
              <div class="mini-card-title">MCP tools</div>
              <div class="mini-card-value">Live market + portfolio tools</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_aws:
        st.markdown(
            """
            <div class="mini-card">
              <div class="mini-card-title">Deployment</div>
              <div class="mini-card-value">AWS ready · ECS · RDS</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def run_chat_prompt(prompt: str, session_id: str, context: str = "") -> dict[str, Any]:
    history_context = chat_history.build_context(session_id)
    combined_context = "\n".join(part for part in [context, history_context] if part)
    chat_history.add_message(session_id, "user", prompt)
    result = supervisor.run(
        question=prompt,
        user_id=session_id,
        conversation_context=combined_context,
    )
    agent_name = result.get("agent", "Agent")
    agent_flow = build_agent_flow(prompt, result)
    answer_with_trace = "\n\n".join(
        [
            f"Agent called: {agent_name}",
            "Internal flow:",
            *[f"- {step}" for step in agent_flow],
            result["answer"],
        ]
    )
    chat_history.add_message(session_id, "assistant", answer_with_trace)
    persist_agent_trace(prompt, result, session_id)
    return result


def persist_agent_trace(prompt: str, result: dict[str, Any], user_id: str) -> None:
    """Store the latest supervisor/agent/tool path for the UI."""

    agent_name = result.get("agent", "Agent")
    agent_flow = build_agent_flow(prompt, result)
    agent_graph = build_agent_graph(prompt, result)
    trace = {
        "question": prompt,
        "user_id": user_id,
        "agent": agent_name,
        "flow": agent_flow,
        "graph": agent_graph,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.session_state["last_agent_call"] = agent_name
    st.session_state["last_agent_flow"] = agent_flow
    st.session_state["last_agent_graph"] = agent_graph
    st.session_state["last_agent_trace"] = trace
    st.session_state.setdefault("agent_trace_history", []).append(trace)
    st.session_state["agent_trace_history"] = st.session_state["agent_trace_history"][-10:]


def persist_tab_agent_trace(
    tab_key: str,
    prompt: str,
    result: dict[str, Any],
    user_id: str,
) -> None:
    """Store the latest agent trace for a specific tab."""

    persist_agent_trace(prompt, result, user_id)
    st.session_state[f"{tab_key}_agent_trace"] = {
        "question": prompt,
        "user_id": user_id,
        "agent": result.get("agent", "Agent"),
        "flow": build_agent_flow(prompt, result),
        "graph": build_agent_graph(prompt, result),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def render_agent_flow_trace(
    prompt: str,
    result: dict[str, Any],
    *,
    title: str = "Internal agent flow for this question",
) -> None:
    """Render a readable flow chart and step-by-step call trace."""

    agent_name = result.get("agent", "Agent")
    graph = build_agent_graph(prompt, result)
    flow = build_agent_flow(prompt, result)

    st.markdown(f"### {title}")
    meta_col_question, meta_col_agent = st.columns([3, 1])
    meta_col_question.caption(f"Question: {prompt}")
    meta_col_agent.metric("Agent selected", agent_name)

    try:
        st.graphviz_chart(graph, width="stretch")
    except Exception as exc:
        st.warning(f"Flow chart could not render, showing step flow instead: {exc}")

    with st.expander("Step-by-step agent calls", expanded=True):
        for index, step in enumerate(flow, start=1):
            st.markdown(f"{index}. {step}")


def render_saved_tab_agent_trace(tab_key: str, empty_message: str) -> None:
    """Render the latest saved flow chart for a tab even after Streamlit reruns."""

    if tab_key != "chatbot":
        return

    trace = st.session_state.get(f"{tab_key}_agent_trace")
    if not trace:
        st.info(empty_message)
        return

    visible_state_key = f"{tab_key}_agent_trace_visible"
    visible = st.session_state.get(visible_state_key, False)
    button_label = (
        "Hide internal agent flow for this tab"
        if visible
        else "Show internal agent flow for this tab"
    )
    if st.button(button_label, key=f"{tab_key}_agent_trace_button"):
        st.session_state[visible_state_key] = not visible
        st.rerun()

    if not st.session_state.get(visible_state_key, False):
        st.caption(
            f"Latest flow available for: {trace.get('question')} "
            f"({trace.get('agent', 'Agent')})"
        )
        return

    st.markdown("### Internal agent flow for this tab")
    meta_col_question, meta_col_agent, meta_col_time = st.columns([3, 1, 1])
    meta_col_question.caption(f"Question: {trace.get('question')}")
    meta_col_agent.metric("Agent", trace.get("agent", "Agent"))
    meta_col_time.caption(f"Time: {trace.get('created_at')}")

    graph = trace.get("graph")
    if graph:
        try:
            st.graphviz_chart(graph, width="stretch")
        except Exception as exc:
            st.warning(f"Flow chart could not render, showing steps instead: {exc}")

    with st.expander("Step-by-step agent calls", expanded=True):
        for index, step in enumerate(trace.get("flow", []), start=1):
            st.markdown(f"{index}. {step}")


def build_agent_flow(prompt: str, result: dict[str, Any]) -> list[str]:
    normalized = prompt.lower()
    agent_name = result.get("agent", "Agent")

    if agent_name == "Stock Agent":
        if any(
            phrase in normalized
            for phrase in ["best stock", "suggest", "recommend", "top stock", "this month"]
        ):
            tool_name = "MCP tool: suggest_best_stock_of_month"
        elif any(
            phrase in normalized
            for phrase in [
                "5 year",
                "5-year",
                "five year",
                "five-year",
                "3 year",
                "3-year",
                "three year",
                "monthly",
                "performance",
                "profit",
                "loss",
                "analysis",
                "analyse",
                "analyze",
            ]
        ):
            tool_name = "MCP tool: stock_performance_analysis"
        else:
            tool_name = "MCP tool: stock_research"
        return [
            "Chatbot receives user question",
            "LangGraph Supervisor routes question to Stock Agent",
            f"Stock Agent calls {tool_name}",
            "MCP tool fetches live market data from Yahoo Finance via yfinance",
            "Supervisor also calls Portfolio Agent for selected user's holdings and risk context",
            "Portfolio Agent calls MCP tool: portfolio_analysis using SQLite holdings and Yahoo Finance prices",
            "Stock Agent formats answer and stores it in chat history",
        ]

    if agent_name == "RAG Agent":
        return [
            "Chatbot receives report/document question",
            "LangGraph Supervisor routes question to RAG Agent",
            "RAG Agent extracts uploaded PDF/TXT/MD text when a file is provided",
            "RAG Agent chunks text and retrieves relevant chunks",
            "RAG Agent returns a grounded document answer and stores it in chat history",
        ]

    if agent_name == "Portfolio Agent":
        return [
            "Chatbot receives portfolio/risk question",
            "LangGraph Supervisor routes question to Portfolio Agent",
            "Portfolio Agent calls MCP tool: portfolio_analysis",
            "MCP reads user holdings from SQLite seed database",
            "MCP fetches live prices from Yahoo Finance and calculates risk alerts",
            "Portfolio Agent returns portfolio summary and stores it in chat history",
        ]

    if agent_name == "User Agent":
        return [
            "Chatbot receives profile/watchlist question",
            "LangGraph Supervisor routes question to User Agent",
            "User Agent calls MCP tool: user_context",
            "MCP reads user profile/watchlist from SQLite seed database",
            "User Agent returns user context and stores it in chat history",
        ]

    if agent_name == "Investment Agent":
        return [
            "Chatbot receives investment/buy/sell/suggestion question",
            "LangGraph Supervisor routes question to Investment Agent",
            "Investment Agent calls Stock Agent for market data",
            "Investment Agent calls User Agent for profile and risk context",
            "Investment Agent calls Portfolio Agent for holdings and portfolio risk",
            "Bedrock/Nova Lite generates the final educational research summary when available",
            "Investment Agent stores final answer in chat history",
        ]

    return [
        "Chatbot receives user question",
        "LangGraph Supervisor selects the most relevant agent",
        f"{agent_name} returns the final response",
        "Response is stored in chat history",
    ]


def build_agent_graph(prompt: str, result: dict[str, Any]) -> str:
    normalized = prompt.lower()
    agent_name = result.get("agent", "Agent")

    graph_styles = """
    digraph AgentFlow {
      rankdir=LR;
      graph [bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.45"];
      node [shape=box, style="rounded,filled", color="#98a2b3", fillcolor="#f8fafc", fontname="Arial", fontsize=10];
      edge [color="#667085", arrowsize=0.8, fontname="Arial", fontsize=9];
    """

    if agent_name == "Stock Agent":
        if any(
            phrase in normalized
            for phrase in ["best stock", "suggest", "recommend", "top stock", "this month"]
        ):
            tool_label = "suggest_best_stock_of_month"
        elif any(
            phrase in normalized
            for phrase in [
                "5 year",
                "5-year",
                "five year",
                "five-year",
                "3 year",
                "3-year",
                "three year",
                "monthly",
                "performance",
                "profit",
                "loss",
                "analysis",
                "analyse",
                "analyze",
            ]
        ):
            tool_label = "stock_performance_analysis"
        else:
            tool_label = "stock_research"
        return (
            graph_styles
            + f'''
      user [label="User question", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      stock [label="Stock Agent", fillcolor="#dcfce7"];
      mcp [label="MCP tool\\n{tool_label}", fillcolor="#fef3c7"];
      yahoo [label="Yahoo Finance\\nyfinance", fillcolor="#fee2e2"];
      portfolio [label="Portfolio Agent\\ncontext", fillcolor="#dcfce7"];
      pmcp [label="MCP tool\\nportfolio_analysis", fillcolor="#fef3c7"];
      sqlite [label="SQLite\\nholdings", fillcolor="#fee2e2"];
      answer [label="Answer +\\nchat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> stock [label="stock route"];
      stock -> mcp [label="tool call"];
      mcp -> yahoo [label="market data"];
      yahoo -> mcp;
      mcp -> stock;
      supervisor -> portfolio [label="portfolio context"];
      portfolio -> pmcp [label="tool call"];
      pmcp -> sqlite [label="read holdings"];
      pmcp -> yahoo [label="price/risk data"];
      sqlite -> pmcp;
      pmcp -> portfolio;
      portfolio -> stock [label="risk context"];
      stock -> answer;
    }}
    '''
        )

    if agent_name == "RAG Agent":
        return (
            graph_styles
            + '''
      user [label="User question\\n+ uploaded file", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      rag [label="RAG Agent", fillcolor="#dcfce7"];
      extract [label="Extract text\\nPDF/TXT/MD", fillcolor="#fef3c7"];
      chunks [label="Chunk text\\n+ retrieve relevant chunks", fillcolor="#fef3c7"];
      answer [label="Grounded answer\\n+ chat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> rag [label="rag route"];
      rag -> extract;
      extract -> chunks;
      chunks -> rag;
      rag -> answer;
    }
    '''
        )

    if agent_name == "Portfolio Agent":
        return (
            graph_styles
            + '''
      user [label="User question", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      portfolio [label="Portfolio Agent", fillcolor="#dcfce7"];
      mcp [label="MCP tool\\nportfolio_analysis", fillcolor="#fef3c7"];
      sqlite [label="SQLite\\nuser holdings", fillcolor="#fee2e2"];
      yahoo [label="Yahoo Finance\\nlive prices", fillcolor="#fee2e2"];
      risk [label="Risk alerts\\n+ charts data", fillcolor="#fce7f3"];
      answer [label="Answer +\\nchat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> portfolio [label="portfolio route"];
      portfolio -> mcp [label="tool call"];
      mcp -> sqlite [label="read holdings"];
      mcp -> yahoo [label="fetch prices"];
      sqlite -> mcp;
      yahoo -> mcp;
      mcp -> risk;
      risk -> portfolio;
      portfolio -> answer;
    }
    '''
        )

    if agent_name == "User Agent":
        return (
            graph_styles
            + '''
      user [label="User question", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      useragent [label="User Agent", fillcolor="#dcfce7"];
      mcp [label="MCP tool\\nuser_context", fillcolor="#fef3c7"];
      sqlite [label="SQLite\\nprofile/watchlist", fillcolor="#fee2e2"];
      answer [label="Answer +\\nchat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> useragent [label="user route"];
      useragent -> mcp [label="tool call"];
      mcp -> sqlite [label="read user data"];
      sqlite -> mcp;
      mcp -> useragent;
      useragent -> answer;
    }
    '''
        )

    if agent_name == "Investment Agent":
        return (
            graph_styles
            + '''
      user [label="User question", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      invest [label="Investment Agent", fillcolor="#dcfce7"];
      stock [label="Stock Agent", fillcolor="#fef3c7"];
      useragent [label="User Agent", fillcolor="#fef3c7"];
      portfolio [label="Portfolio Agent", fillcolor="#fef3c7"];
      bedrock [label="Amazon Bedrock\\nNova Lite", fillcolor="#fee2e2"];
      answer [label="Educational answer\\n+ chat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> invest [label="investment route"];
      invest -> stock [label="market data"];
      invest -> useragent [label="profile/risk"];
      invest -> portfolio [label="holdings/risk"];
      stock -> invest;
      useragent -> invest;
      portfolio -> invest;
      invest -> bedrock [label="summary prompt"];
      bedrock -> invest;
      invest -> answer;
    }
    '''
        )

    return (
        graph_styles
        + f'''
      user [label="User question", fillcolor="#dbeafe"];
      supervisor [label="LangGraph\\nSupervisor", fillcolor="#ede9fe"];
      agent [label="{agent_name}", fillcolor="#dcfce7"];
      answer [label="Answer +\\nchat history", fillcolor="#e0f2fe"];
      user -> supervisor [label="route"];
      supervisor -> agent [label="selected agent"];
      agent -> answer;
    }}
    '''
    )


def render_recent_chat_preview(session_id: str) -> None:
    messages = chat_history.get_messages(session_id, limit=4)
    if not messages:
        st.info("No recent chat yet.")
        return

    for message in messages[-4:]:
        label = "You" if message.role == "user" else "Assistant"
        with st.container(border=True):
            st.caption(label)
            st.markdown(message.content[:700])


def render_chat_history(session_id: str, limit: int = 30) -> None:
    messages = chat_history.get_messages(session_id, limit=limit)
    if not messages:
        st.info("No chat history yet. Ask a stock, portfolio, or watchlist question.")
        return

    for message in messages:
        avatar = "🧑" if message.role == "user" else "🤖"
        with st.chat_message(message.role, avatar=avatar):
            st.markdown(message.content)
            if message.role != "user":
                st.caption(STOCK_ADVICE_DISCLAIMER)
            st.caption(message.created_at)


def show_agent_routing_help() -> None:
    st.markdown(
        """
        **Chatbot internal routing**

        1. User asks a question in the chatbot.
        2. LangGraph Supervisor reads the question.
        3. Supervisor chooses one specialist agent.
        4. The selected agent calls MCP tools, local RAG, Yahoo Finance, SQLite, or Bedrock as needed.
        5. Final answer is saved in chat history.
        6. The latest flow chart updates for that exact question.

        **Routing rules**

        - Stock Agent: stock price, comparison, performance, profit/loss.
        - RAG Agent: uploaded PDF/TXT/MD reports and document questions.
        - Portfolio Agent: holdings, allocation, portfolio charts, risk alerts.
        - User Agent: user profile, watchlist, risk profile.
        - Investment Agent: buy/sell/right-time/best-stock/suggestion questions.

        **Typical flow examples**

        - Stock price: Chatbot → LangGraph Supervisor → Stock Agent → MCP stock tool → Yahoo Finance.
        - Portfolio risk: Chatbot → LangGraph Supervisor → Portfolio Agent → MCP portfolio tool → SQLite + Yahoo Finance.
        - Uploaded report: Chatbot → LangGraph Supervisor → RAG Agent → extract text → chunk → retrieve → answer.
        - Investment question: Chatbot → LangGraph Supervisor → Investment Agent → Stock + User + Portfolio Agents → Bedrock summary.
        """
    )


st.set_page_config(page_title="Stock Market Agent", layout="wide")
apply_app_styles()

st.markdown(
    """
    <div class="hero-card">
      <h1>Stock Market Agent</h1>
      <p>Research stocks, review portfolio risk, analyze reports, and keep chat history in one clean dashboard.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

mcp_client = McpClient.from_settings()
settings = get_settings()
chat_history = ChatHistoryService.from_settings(settings)
supervisor = LangGraphSupervisor(
    stock_agent=StockAgent(mcp_client),
    rag_agent=RagAgent(mcp_client),
    user_agent=UserAgent(mcp_client),
    portfolio_agent=PortfolioAgent(mcp_client),
)

with st.sidebar:
    st.header("💬 Stock Chatbot")
    session_id = st.text_input("Chat / User ID", value="demo-user", key="chat_session")
    st.caption("Past messages are saved and reused as context.")

    chat_actions_col, chat_refresh_col = st.columns(2)
    with chat_actions_col:
        if st.button("Clear", width="stretch"):
            chat_history.clear_session(session_id)
            st.rerun()
    with chat_refresh_col:
        if st.button("Refresh", width="stretch"):
            st.rerun()

    messages = chat_history.get_messages(session_id)
    saved_col, agent_col = st.columns(2)
    saved_col.metric("Messages", len(messages))
    agent_col.metric("Last agent", st.session_state.get("last_agent_call", "None"))

    sidebar_prompt = st.text_area(
        "Ask the assistant",
        placeholder="Example: compare Apple and Meta, or analyze my portfolio",
        key="sidebar_chat_prompt",
        height=90,
    )

    if st.button("Send", type="primary", width="stretch"):
        if not sidebar_prompt.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Agent is thinking..."):
                run_chat_prompt(sidebar_prompt, session_id)
            st.rerun()

    st.subheader("Recent chat")
    render_recent_chat_preview(session_id)

    flow_visible = st.session_state.get("chatbot_agent_flow_visible", False)
    flow_button_label = (
        "Hide internal agent flow for chatbot"
        if flow_visible
        else "Show internal agent flow for chatbot"
    )
    if st.button(flow_button_label, key="chatbot_agent_flow_button", width="stretch"):
        st.session_state["chatbot_agent_flow_visible"] = not flow_visible
        st.rerun()

    if st.session_state.get("chatbot_agent_flow_visible", False):
        with st.container(border=True):
            st.markdown("#### Internal agent flow for chatbot")
            last_trace = st.session_state.get("last_agent_trace")
            last_flow = st.session_state.get("last_agent_flow", [])
            last_graph = st.session_state.get("last_agent_graph")
            if last_flow:
                if last_trace:
                    st.caption(
                        f"Question: {last_trace.get('question')} | "
                        f"User: {last_trace.get('user_id')} | "
                        f"Time: {last_trace.get('created_at')}"
                    )
                if last_graph:
                    try:
                        st.graphviz_chart(last_graph, width="stretch")
                    except Exception as exc:
                        st.warning(f"Flow chart could not render: {exc}")
                for index, step in enumerate(last_flow, start=1):
                    st.markdown(f"{index}. {step}")
            else:
                st.info("Ask a chatbot question to see the supervisor-to-agent flow chart.")

    with st.expander("Recent agent flow history", expanded=False):
        trace_history = st.session_state.get("agent_trace_history", [])
        if not trace_history:
            st.info("No agent flow history yet.")
        else:
            for trace in reversed(trace_history[-5:]):
                st.markdown(
                    f"**{trace.get('created_at')} | {trace.get('agent')} | "
                    f"{trace.get('user_id')}**"
                )
                st.caption(trace.get("question", ""))
                for index, step in enumerate(trace.get("flow", []), start=1):
                    st.markdown(f"{index}. {step}")
                st.divider()

    with st.expander("Full chat history", expanded=False):
        render_chat_history(session_id)

tab_research, tab_portfolio, tab_watchlist, tab_settings = st.tabs(
    ["🔎 Agent Research", "📊 My Portfolio", "⭐ My Watchlist", "⚙️ Settings"]
)

with tab_research:
    st.markdown("### Ask the Stock Agent")
    st.caption(
        "Ask for stock prices, comparisons, 5-year performance, profit/loss scenarios, "
        "or uploaded report analysis."
    )
    uploaded_file = st.file_uploader(
        "Upload a PDF or text financial report",
        type=["pdf", "txt", "md"],
    )
    question = st.text_area(
        "Question",
        placeholder="Example: compare Apple and Meta, or analyse this uploaded report",
    )

    if st.button("Run research", type="primary"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            history_context = chat_history.build_context(session_id)
            chat_history.add_message(session_id, "user", question)
            result = supervisor.run(
                question=question,
                user_id=session_id,
                uploaded_file=uploaded_file,
                conversation_context=history_context,
            )
            persist_tab_agent_trace("research", question, result, session_id)
            chat_history.add_message(session_id, "assistant", result["answer"])
            st.subheader(result["agent"])
            st.write(result["answer"])
            show_stock_advice_disclaimer()

            if result.get("sources"):
                st.caption("Sources")
                st.write(result["sources"])

    render_saved_tab_agent_trace(
        "research",
        "Run an Agent Research question to see the exact Supervisor → Agent → Tool flow.",
    )

with tab_portfolio:
    st.subheader("Portfolio dashboard")
    st.caption("Select a seeded investor profile or type a user ID to analyze holdings, charts, and risk alerts.")
    if "investment_users" not in st.session_state:
        st.session_state["investment_users"] = fetch_investment_users(mcp_client)

    investment_users = st.session_state.get("investment_users", [])
    user_options = ["demo-user"] + [user["user_id"] for user in investment_users]
    selected_portfolio_user = st.selectbox(
        "Select portfolio user",
        options=user_options,
        format_func=lambda option: user_option_label(option, investment_users),
        key="portfolio_user_select",
    )
    manual_portfolio_user = st.text_input(
        "Or enter User ID manually",
        value="",
        placeholder="Example: user-technology-001",
        key="portfolio_user",
    )
    user_id = manual_portfolio_user.strip() or selected_portfolio_user

    selected_user_profile = next(
        (user for user in investment_users if user["user_id"] == user_id),
        None,
    )
    if selected_user_profile:
        name_col, id_col, sector_col, risk_col = st.columns(4)
        name_col.metric("User name", selected_user_profile.get("display_name", user_id))
        id_col.metric("User ID", user_id)
        sector_col.metric("Sector", selected_user_profile["sector"])
        risk_col.metric("Risk profile", selected_user_profile["risk_profile"])
        st.caption(
            f"Watchlist: {', '.join(selected_user_profile['watchlist'])}"
        )
    else:
        name_col, id_col = st.columns(2)
        name_col.metric("User name", "Manual user")
        id_col.metric("User ID", user_id)

    if st.button("Analyze portfolio"):
        portfolio_question = "analyze my portfolio"
        result = supervisor.run(question=portfolio_question, user_id=user_id)
        persist_tab_agent_trace("portfolio", portfolio_question, result, user_id)
        data = result.get("data", {})

        st.markdown("### Portfolio summary")
        total_value = data.get("total_value")
        total_gain_loss = data.get("total_gain_loss")
        total_gain_loss_percent = data.get("total_gain_loss_percent")

        if total_value is not None:
            col_value, col_gain, col_gain_pct = st.columns(3)
            col_value.metric("Total value", f"${total_value:,.2f}")
            col_gain.metric("Total gain/loss", f"${total_gain_loss or 0:,.2f}")
            col_gain_pct.metric("Gain/loss %", f"{total_gain_loss_percent or 0:+.2f}%")
        else:
            st.write(result["answer"])

        holdings = data.get("holdings", [])
        if holdings:
            st.markdown("### Holdings")
            holdings_df = pd.DataFrame(holdings)
            st.dataframe(holdings_df, width="stretch")

            chart_df = holdings_df.copy()
            chart_df["allocation_percent"] = (
                chart_df["market_value"] / chart_df["market_value"].sum() * 100
                if chart_df["market_value"].sum()
                else 0
            )

            st.markdown("### Portfolio charts")
            allocation_col, gain_loss_col = st.columns(2)

            with allocation_col:
                st.caption("Allocation pie by market value")
                render_allocation_pie(chart_df)

            with gain_loss_col:
                st.caption("Gain / loss by stock")
                render_gain_loss_chart(chart_df)

            with st.expander("Allocation bar chart"):
                st.bar_chart(
                    chart_df.set_index("ticker")["market_value"],
                    width="stretch",
                )

            with st.expander("Allocation percentages"):
                st.dataframe(
                    chart_df[["ticker", "market_value", "allocation_percent", "gain_loss"]],
                    width="stretch",
                    column_config={
                        "market_value": st.column_config.NumberColumn(
                            "Market value",
                            format="$%.2f",
                        ),
                        "allocation_percent": st.column_config.NumberColumn(
                            "Allocation %",
                            format="%.2f%%",
                        ),
                        "gain_loss": st.column_config.NumberColumn(
                            "Gain / loss",
                            format="$%.2f",
                        ),
                    },
                )

            render_portfolio_recommendations(
                selected_user_profile,
                holdings,
                mcp_client,
            )

        st.markdown("### Risk alerts")
        render_risk_alert_chart(data)
        show_portfolio_risk_alerts(data)
        risk_alerts = []
        if risk_alerts:
            for alert in risk_alerts:
                if "No major" in alert:
                    st.success(alert)
                else:
                    st.warning(f"⚠️ {alert}")
        elif False:
            st.info("No portfolio risk alerts returned.")

        with st.expander("Full Portfolio Agent response"):
            st.write(result["answer"])
        show_stock_advice_disclaimer()

    render_saved_tab_agent_trace(
        "portfolio",
        "Click Analyze portfolio to see the exact Supervisor → Portfolio Agent → MCP flow.",
    )

with tab_watchlist:
    st.subheader("Watchlist dashboard")
    st.caption("Review a selected user's watchlist, live price chart, and Top 10 market snapshot.")
    if "investment_users" not in st.session_state:
        st.session_state["investment_users"] = fetch_investment_users(mcp_client)

    investment_users = st.session_state.get("investment_users", [])
    user_options = ["demo-user"] + [user["user_id"] for user in investment_users]
    selected_watchlist_user = st.selectbox(
        "Select watchlist user",
        options=user_options,
        format_func=lambda option: user_option_label(option, investment_users),
        key="watchlist_user_select",
    )
    manual_watchlist_user = st.text_input(
        "Or enter User ID manually",
        value="",
        placeholder="Example: user-healthcare-003",
        key="watchlist_user",
    )
    user_id = manual_watchlist_user.strip() or selected_watchlist_user

    selected_user_profile = next(
        (user for user in investment_users if user["user_id"] == user_id),
        None,
    )
    if selected_user_profile:
        st.caption(
            f"Name: {selected_user_profile.get('display_name', user_id)} | "
            f"Sector: {selected_user_profile['sector']} | "
            f"Risk: {selected_user_profile['risk_profile']} | "
            f"Watchlist: {', '.join(selected_user_profile['watchlist'])}"
        )

    col_watchlist, col_refresh = st.columns([1, 1])
    with col_watchlist:
        if st.button("Show my saved watchlist", width="stretch"):
            watchlist_prompt = "show my watchlist"
            result = supervisor.run(question=watchlist_prompt, user_id=user_id)
            persist_tab_agent_trace("watchlist", watchlist_prompt, result, user_id)
            st.info(result["answer"])
            show_stock_advice_disclaimer()

    with col_refresh:
        refresh_clicked = st.button("Refresh live Top 10 stocks", type="primary", width="stretch")

    selected_watchlist = (
        selected_user_profile.get("watchlist", [])
        if selected_user_profile
        else TOP_10_STOCKS
    )
    st.markdown("### My Watchlist price chart")
    if selected_watchlist:
        watchlist_state_key = f"watchlist_quotes_{user_id}"
        refresh_saved_watchlist = st.button(
            "Refresh my watchlist chart",
            width="stretch",
            key="refresh_saved_watchlist",
        )
        if refresh_saved_watchlist or watchlist_state_key not in st.session_state:
            with st.spinner("Fetching selected watchlist prices from MCP..."):
                st.session_state[watchlist_state_key] = fetch_live_quotes(
                    mcp_client,
                    selected_watchlist,
                )

        watchlist_rows = st.session_state.get(watchlist_state_key, [])
        if watchlist_rows:
            watchlist_df = pd.DataFrame(watchlist_rows)
            st.bar_chart(
                watchlist_df.set_index("Ticker")["Price"],
                width="stretch",
            )
            with st.expander("Watchlist price table"):
                st.dataframe(
                    watchlist_df,
                    width="stretch",
                    column_config={
                        "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                        "Previous Close": st.column_config.NumberColumn(
                            "Previous Close",
                            format="$%.2f",
                        ),
                    },
                )
        else:
            st.warning("No saved watchlist price data is available yet.")
    else:
        st.info("No saved watchlist stocks found for this user.")

    if refresh_clicked or "top_10_quotes" not in st.session_state:
        with st.spinner("Fetching live Top 10 stock prices from MCP..."):
            st.session_state["top_10_quotes"] = fetch_live_top_10_quotes(mcp_client)
            st.session_state["top_10_refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    st.markdown("### Live Top 10 stocks")
    st.caption(f"Last refreshed: {st.session_state.get('top_10_refreshed_at', 'Not refreshed yet')}")

    top_10_rows = st.session_state.get("top_10_quotes", [])
    if top_10_rows:
        top_10_df = pd.DataFrame(top_10_rows)
        st.dataframe(
            top_10_df,
            width="stretch",
            column_config={
                "Price": st.column_config.NumberColumn("Price", format="$%.2f"),
                "Previous Close": st.column_config.NumberColumn("Previous Close", format="$%.2f"),
            },
        )
    else:
        st.warning("No live Top 10 stock data is available yet.")

    with st.expander("Ask Watchlist Agent"):
        watchlist_question = st.text_area(
            "Watchlist question",
            placeholder="Example: which stocks are in my watchlist?",
            key="watchlist_question",
        )
        if st.button("Run watchlist question"):
            if not watchlist_question.strip():
                st.warning("Please enter a watchlist question.")
            else:
                result = supervisor.run(question=watchlist_question, user_id=user_id)
                persist_tab_agent_trace("watchlist", watchlist_question, result, user_id)
                st.write(result["answer"])
                show_stock_advice_disclaimer()

    render_saved_tab_agent_trace(
        "watchlist",
        "Run a Watchlist question to see the exact Supervisor → User Agent → MCP flow.",
    )

with tab_settings:
    st.subheader("Configuration")
    st.write("This app connects to the shared MCP server configured by `MCP_SERVER_URL`.")
    st.code(mcp_client.server_url or "MCP_SERVER_URL is not configured")
