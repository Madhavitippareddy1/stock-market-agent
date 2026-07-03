# Langfuse and RAGAS Implementation

This project includes Langfuse observability and RAGAS-style RAG evaluation.

## What Langfuse captures

Each user question routed through `LangGraphSupervisor.run()` creates one
Langfuse trace when Langfuse is enabled.

Trace metadata includes:

- user ID / session ID
- question
- selected route
- selected agent
- answer output
- source count
- upload flag
- conversation-context length

Implementation file:

```text
src/stock_market_agent/services/observability.py
```

Supervisor integration:

```text
src/stock_market_agent/graphs/langgraph_supervisor.py
```

## What RAGAS captures

RAG answers include deterministic RAGAS-compatible quality scores:

- `ragas_context_precision`
- `ragas_answer_relevancy`
- `ragas_faithfulness`
- `ragas_context_recall`
- `ragas_passed`

The scores are added to:

1. `result["data"]["ragas"]` so Streamlit can render them.
2. Langfuse trace scores when Langfuse is enabled.

RAG Agent integration:

```text
src/stock_market_agent/agents/rag_agent.py
```

## Why deterministic RAGAS-style scores

The project installs `ragas`, but live LLM-as-judge evaluation can add latency
and Bedrock cost to every user request. For production UI usage, the current
implementation uses deterministic RAGAS-compatible metrics that are fast and
safe for every RAG request.

Later, a scheduled/offline evaluation job can use the full `ragas` package with
golden datasets and LLM judges.

## Streamlit UI

The Agent Research tab now shows a `RAGAS evaluation` panel when the selected
agent is RAG and score data is available.

It displays:

- score metrics
- pass/fail quality gate
- raw score JSON

## Required environment variables

```text
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=<your-public-key>
LANGFUSE_SECRET_KEY=<your-secret-key>
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_FLUSH_ON_REQUEST=false

RAGAS_ENABLED=true
RAGAS_SCORE_PREFIX=ragas
RAGAS_MIN_CONTEXT_PRECISION=0.45
RAGAS_MIN_FAITHFULNESS=0.55
```

For AWS ECS, store `LANGFUSE_SECRET_KEY` in AWS Secrets Manager. Do not commit
the secret key to GitHub.

## AWS deployment note

The full CloudFormation template includes Langfuse and RAGAS parameters:

```text
infra/cloudformation/stock-market-agent.yml
```

The current running ECS service was created before this change. To activate
Langfuse on the running service, refresh AWS credentials and then update the
ECS task definition or CloudFormation stack with the Langfuse values.

## Validation

Local tests:

```powershell
python -m pytest
```

Current validation result after implementation:

```text
16 passed
```
## Publishing prompt versions to Langfuse

System prompts and user prompt templates are version-controlled in:

```text
data/prompts/prompts.json
```

To publish the local prompt catalogue to Langfuse Prompt Management, run:

```bash
uv run python scripts/publish_langfuse_prompts.py
```

The script creates chat prompts named with the `stock-market-agent/` prefix, for example:

- `stock-market-agent/investment_research_summary`
- `stock-market-agent/trajectory_judge`

Each semantic version from the JSON catalogue is added as a Langfuse label, for example `v1.2.0`. The active prompt version also receives `latest` and the active environment label, for example `production`.

Use dry-run mode before publishing changes:

```bash
uv run python scripts/publish_langfuse_prompts.py --dry-run
```
