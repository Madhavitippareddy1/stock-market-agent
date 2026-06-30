# LangGraph and Amazon Bedrock

This project uses LangGraph for agent orchestration and Amazon Bedrock for LLM
generation and embeddings.

## LangGraph role

LangGraph is used in:

```text
src/stock_market_agent/graphs/langgraph_supervisor.py
```

The graph routes user requests to:

- Stock Agent
- RAG Agent
- User Agent
- Portfolio Agent
- Investment Agent

Routing examples:

| User request | Route |
| --- | --- |
| `Cisco Systems share price` | Stock Agent |
| `analyse this report` | RAG Agent |
| `show my watchlist` | User Agent |
| `analyze my portfolio` | Portfolio Agent |
| `should I buy PepsiCo?` | Investment Agent |

## Bedrock role

Bedrock is wrapped in:

```text
src/stock_market_agent/services/bedrock_service.py
```

Configured models:

```text
BEDROCK_CHAT_MODEL_ID=amazon.nova-lite-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
```

Current usage:

- Nova Lite through Bedrock Converse for Investment Agent summaries.
- Titan Text Embeddings V2 through Bedrock Runtime for future RAG embeddings.

## Flow

```text
Streamlit
  -> LangGraphSupervisor
  -> Specialist agents
  -> Shared MCP server tools
  -> Bedrock generation for investment summary
```

If Bedrock is unavailable locally, the service returns a safe fallback message
instead of crashing the app.
