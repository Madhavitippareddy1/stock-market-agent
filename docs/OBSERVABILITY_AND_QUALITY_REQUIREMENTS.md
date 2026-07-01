# Observability and Quality Measurement Requirements

This document maps the project implementation to the required capstone checklist.

## 1. Observability dashboard

Implemented in Streamlit:

```text
app.py -> Observability tab
src/stock_market_agent/services/metrics.py
```

The dashboard tracks:

- request volume
- average latency
- p50 latency
- p95 latency
- error rate
- LLM token usage
- estimated Bedrock cost
- average cost per request
- recent request and LLM call events

Metrics are stored in append-only JSONL:

```text
data/observability_metrics.jsonl
```

This is a lightweight Grafana-equivalent dashboard inside the project UI. It can
later be exported to CloudWatch Metrics or Grafana.

## 2. LLM-specific monitoring

Implemented with Langfuse:

```text
src/stock_market_agent/services/observability.py
src/stock_market_agent/graphs/langgraph_supervisor.py
src/stock_market_agent/services/bedrock_service.py
```

Tracked information:

- user question
- selected route
- selected agent
- response output
- sources
- prompt name
- prompt version
- token usage estimate or Bedrock usage
- latency
- estimated cost
- RAGAS scores

AWS ECS uses:

```text
LANGFUSE_ENABLED=true
LANGFUSE_SECRET_KEY from AWS Secrets Manager
LANGFUSE_PUBLIC_KEY from AWS Secrets Manager
LANGFUSE_BASE_URL from AWS Secrets Manager
```

## 3. Prompt catalogue and versioning

Implemented as a version-controlled JSON prompt catalogue:

```text
data/prompts/prompts.json
src/stock_market_agent/services/prompt_catalog.py
```

The Investment Agent no longer hard-codes the Bedrock prompt. It pulls the active
prompt version at runtime:

```text
investment_research_summary -> active_version v1.0.0
```

The catalogue also contains a second prompt version, `v1.1.0`, for A/B
comparison and future prompt experiments.

## 4. Golden dataset

Implemented:

```text
data/evaluation/golden_dataset.json
```

The dataset contains 24 examples, covering:

- stock price questions
- stock comparison
- RAG/report analysis
- portfolio analysis
- watchlist/user profile
- investment questions
- edge cases

This exceeds the requirement of at least 20 examples.

## 5. RAGAS evaluation

Implemented:

```text
src/stock_market_agent/services/observability.py
src/stock_market_agent/agents/rag_agent.py
```

Metrics computed:

- `ragas_context_precision`
- `ragas_answer_relevancy`
- `ragas_faithfulness`
- `ragas_context_recall`
- `ragas_passed`

Scores are:

1. shown in the Streamlit Agent Research tab
2. sent to Langfuse as trace scores
3. included in `result["data"]["ragas"]`

## 6. Additional evaluation method

Implemented deterministic trajectory grading:

```text
src/stock_market_agent/services/evaluation.py
scripts/run_quality_evaluation.py
```

Trajectory grading checks:

- expected specialist agent
- actual selected agent
- source/context availability
- prompt version availability for Investment Agent

This is an additional evaluation method beyond RAGAS and can run in CI without
LLM cost.

## 7. Run evaluation locally

```powershell
python scripts/run_quality_evaluation.py --mode dry-run
```

Default report output:

```text
data/evaluation/latest_quality_report.json
```

## 8. CI/CD

All code is committed to GitHub. CodePipeline builds the Docker image, runs
tests, pushes to ECR, and deploys ECS.

Before shipping a change:

```powershell
python -m pytest
python scripts/run_quality_evaluation.py --mode dry-run
```
