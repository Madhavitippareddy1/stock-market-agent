from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from stock_market_agent.agents.portfolio_agent import PortfolioAgent
from stock_market_agent.agents.rag_agent import RagAgent
from stock_market_agent.agents.stock_agent import StockAgent
from stock_market_agent.agents.user_agent import UserAgent
from stock_market_agent.models import AgentResult
from stock_market_agent.services.bedrock_service import BedrockService
from stock_market_agent.services.metrics import get_metrics_service
from stock_market_agent.services.observability import get_observability
from stock_market_agent.services.prompt_catalog import get_prompt_catalog


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
        observability = get_observability()
        with observability.trace_agent_run(
            name="stock-market-agent-request",
            question=question,
            user_id=user_id,
            session_id=user_id,
            metadata={
                "has_uploaded_file": uploaded_file is not None,
                "conversation_context_chars": len(conversation_context or ""),
            },
        ) as span:
            timer = get_metrics_service().start_request(question=question, user_id=user_id)
            try:
                final_state = self.graph.invoke(state)
                result = final_state["result"]
                route = final_state.get("route")
                timer.finish(
                    agent=result.get("agent", "Agent"),
                    route=route,
                    success=True,
                    metadata={"source_count": len(result.get("sources", []))},
                )
            except Exception as exc:
                timer.finish(
                    agent="Unknown",
                    route=None,
                    success=False,
                    error=str(exc),
                )
                raise
            if span is not None:
                try:
                    span.update(
                        output={
                            "agent": result.get("agent"),
                            "route": route,
                            "answer": result.get("answer"),
                            "sources": result.get("sources", []),
                        },
                        metadata={
                            "route": route,
                            "agent": result.get("agent"),
                            "source_count": len(result.get("sources", [])),
                        },
                    )
                    span.score_trace(
                        name="source_count",
                        value=float(len(result.get("sources", []))),
                        data_type="NUMERIC",
                        comment="Number of sources returned by the selected agent.",
                    )
                except Exception:
                    pass
            return result

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

        prompt_template = get_prompt_catalog().get("investment_research_summary")
        prompt = prompt_template.render(
            conversation_context=state.get("conversation_context", ""),
            question=state["question"],
            stock_answer=stock_result.answer,
            user_answer=user_result.answer,
            portfolio_answer=portfolio_result.answer,
        )
        generated = self.bedrock_service.generate_text(
            prompt,
            system_prompt=prompt_template.system_prompt,
            prompt_name=prompt_template.name,
            prompt_version=prompt_template.version,
            max_tokens=int((prompt_template.metadata or {}).get("max_tokens", 700)),
            temperature=float((prompt_template.metadata or {}).get("temperature", 0.2)),
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
                "prompt": {
                    "name": prompt_template.name,
                    "version": prompt_template.version,
                },
            },
        ).model_dump()
        return {**state, "result": result}
