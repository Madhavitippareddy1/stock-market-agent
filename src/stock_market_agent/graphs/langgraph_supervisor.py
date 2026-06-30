from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.models import AgentResult
from stock_market_agent.services.bedrock_service import BedrockService


RouteName = Literal["stock", "rag", "user", "portfolio", "investment"]


class AgentState(TypedDict, total=False):
    question: str
    conversation_context: str
    user_id: str
    uploaded_file: Any | None
    route: RouteName
    result: dict[str, Any]


class LangGraphSupervisor:
    """LangGraph workflow for routing requests to specialist agents."""

    def __init__(
        self,
        *,
        stock_agent: StockAgent,
        rag_agent: RagAgent,
        user_agent: UserAgent,
        portfolio_agent: PortfolioAgent,
        bedrock_service: BedrockService | None = None,
    ) -> None:
        self.stock_agent = stock_agent
        self.rag_agent = rag_agent
        self.user_agent = user_agent
        self.portfolio_agent = portfolio_agent
        self.bedrock_service = bedrock_service or BedrockService()
        self.graph = self._build_graph()

    def run(
        self,
        question: str,
        *,
        user_id: str = "demo-user",
        uploaded_file: Any | None = None,
        conversation_context: str = "",
    ) -> dict[str, Any]:
        state: AgentState = {
            "question": question,
            "conversation_context": conversation_context,
            "user_id": user_id,
            "uploaded_file": uploaded_file,
        }
        final_state = self.graph.invoke(state)
        return final_state["result"]

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("route", self._route_node)
        workflow.add_node("stock", self._stock_node)
        workflow.add_node("rag", self._rag_node)
        workflow.add_node("user", self._user_node)
        workflow.add_node("portfolio", self._portfolio_node)
        workflow.add_node("investment", self._investment_node)

        workflow.set_entry_point("route")
        workflow.add_conditional_edges(
            "route",
            self._route_selector,
            {
                "stock": "stock",
                "rag": "rag",
                "user": "user",
                "portfolio": "portfolio",
                "investment": "investment",
            },
        )
        workflow.add_edge("stock", END)
        workflow.add_edge("rag", END)
        workflow.add_edge("user", END)
        workflow.add_edge("portfolio", END)
        workflow.add_edge("investment", END)
        return workflow.compile()

    def _route_node(self, state: AgentState) -> AgentState:
        question = state["question"].lower()
        uploaded_file = state.get("uploaded_file")

        if uploaded_file is not None or any(word in question for word in ["report", "pdf", "document"]):
            route: RouteName = "rag"
        elif any(word in question for word in ["portfolio", "holding", "risk alert"]):
            route = "portfolio"
        elif any(word in question for word in ["watchlist", "risk profile", "my profile"]):
            route = "user"
        elif any(
            word in question
            for word in [
                "buy",
                "sell",
                "should i",
                "right time",
                "invest",
                "best stock",
                "suggest",
                "recommend",
                "top stock",
                "this month",
            ]
        ):
            route = "investment"
        else:
            route = "stock"

        return {**state, "route": route}

    def _route_selector(self, state: AgentState) -> RouteName:
        return state["route"]

    def _stock_node(self, state: AgentState) -> AgentState:
        stock_result = self.stock_agent.answer(state["question"])
        portfolio_result = self.portfolio_agent.answer(
            state.get("user_id", "demo-user"),
            "analyze my portfolio",
        )
        portfolio_data = portfolio_result.data or {}
        portfolio_summary_lines = [
            "Portfolio analysis context:",
        ]
        if portfolio_data.get("total_value") is not None:
            portfolio_summary_lines.extend(
                [
                    f"- Portfolio value: ${portfolio_data.get('total_value', 0):,.2f}",
                    f"- Portfolio gain/loss: ${portfolio_data.get('total_gain_loss', 0):,.2f} "
                    f"({portfolio_data.get('total_gain_loss_percent', 0):+.2f}%)",
                ]
            )
        risk_alerts = portfolio_data.get("risk_alerts", [])
        if risk_alerts:
            portfolio_summary_lines.append("- Key portfolio risks:")
            portfolio_summary_lines.extend([f"  - {alert}" for alert in risk_alerts[:3]])
        else:
            portfolio_summary_lines.append("- No portfolio risk alerts were returned.")

        answer = "\n\n".join(
            [
                stock_result.answer,
                "\n".join(portfolio_summary_lines),
                "Portfolio note: Use this as educational context only, not a buy/sell instruction.",
            ]
        )
        result = AgentResult(
            agent=stock_result.agent,
            answer=answer,
            sources=list(dict.fromkeys(stock_result.sources + portfolio_result.sources)),
            data={
                **stock_result.data,
                "portfolio": portfolio_result.data,
            },
        ).model_dump()
        return {**state, "result": result}

    def _rag_node(self, state: AgentState) -> AgentState:
        result = self.rag_agent.answer(
            question=state["question"],
            uploaded_file=state.get("uploaded_file"),
        ).model_dump()
        return {**state, "result": result}

    def _user_node(self, state: AgentState) -> AgentState:
        result = self.user_agent.answer(
            user_id=state.get("user_id", "demo-user"),
            question=state["question"],
        ).model_dump()
        return {**state, "result": result}

    def _portfolio_node(self, state: AgentState) -> AgentState:
        result = self.portfolio_agent.answer(
            user_id=state.get("user_id", "demo-user"),
            question=state["question"],
        ).model_dump()
        return {**state, "result": result}

    def _investment_node(self, state: AgentState) -> AgentState:
        stock_result = self.stock_agent.answer(state["question"])
        user_result = self.user_agent.answer(state.get("user_id", "demo-user"), "show my profile")
        portfolio_result = self.portfolio_agent.answer(
            state.get("user_id", "demo-user"),
            "analyze my portfolio",
        )

        prompt = "\n\n".join(
            [
                "Create an educational investment research summary.",
                f"Conversation context:\n{state.get('conversation_context', '')}",
                f"User question: {state['question']}",
                f"Stock data:\n{stock_result.answer}",
                f"User context:\n{user_result.answer}",
                f"Portfolio context:\n{portfolio_result.answer}",
                (
                    "Return: direct summary, positives, risks, portfolio fit, "
                    "next research steps, and disclaimer."
                ),
            ]
        )
        generated = self.bedrock_service.generate_text(
            prompt,
            system_prompt=(
                "You are a financial research assistant. Do not provide guaranteed "
                "financial advice. Be clear, balanced, and include risk."
            ),
        )
        if generated.startswith("Bedrock generation unavailable"):
            answer = "\n\n".join(
                [
                    "Investment research summary:",
                    stock_result.answer,
                    "Portfolio context:",
                    portfolio_result.answer,
                    generated,
                    "Disclaimer: Educational research only, not financial advice.",
                ]
            )
        else:
            answer = generated

        result = AgentResult(
            agent="Investment Agent",
            answer=answer,
            sources=list(
                dict.fromkeys(
                    stock_result.sources + user_result.sources + portfolio_result.sources
                )
            ),
            data={
                "stock": stock_result.data,
                "user": user_result.data,
                "portfolio": portfolio_result.data,
            },
        ).model_dump()
        return {**state, "result": result}
