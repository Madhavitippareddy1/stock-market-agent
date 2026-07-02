# Stock Market Agent

A FastAPI backend plus Streamlit frontend multi-agent stock research application.

This project is the clean new version of the stock agent platform. It is
designed to use a shared MCP server for tools, AWS for deployment, and
CodePipeline instead of GitHub Actions.

## Agents

- Stock Agent: stock quote, company profile, market data, comparison.
- RAG Agent: PDF/text report analysis and financial-report search.
- User Agent: user profile, watchlist, risk preference.
- Portfolio Agent: holdings, allocation, gain/loss, risk alerts.
- Investment Agent: LangGraph route that uses stock/user/portfolio context and
  Amazon Bedrock for educational investment research.

## LLM and orchestration

- LangGraph orchestrates the multi-agent routing.
- Amazon Bedrock is used as the LLM platform.
- Amazon Nova Lite is configured for generation.
- Amazon Titan Text Embeddings V2 is configured for embeddings.

See `docs/LANGGRAPH_BEDROCK.md`.

## Observability and RAG evaluation

- Langfuse captures chatbot/agent traces when enabled.
- RAGAS-compatible scores are generated for RAG answers and shown in Streamlit.
- Scores are also sent to Langfuse as trace scores when credentials are configured.

See `docs/LANGFUSE_RAGAS.md`.
See `docs/OBSERVABILITY_AND_QUALITY_REQUIREMENTS.md` for the dashboard,
prompt catalogue, golden dataset, RAGAS, and trajectory evaluation checklist.

## Shared MCP server

This project does not create a separate MCP server. It connects to the common
MCP server used by your five projects.

Required MCP tools are documented in:

- `docs/MCP_TOOLS_CONTRACT.md`

## AWS deployment

The deployment design uses:

- Streamlit
- Docker
- Amazon ECR
- Amazon ECS Fargate
- AWS CodePipeline
- AWS CodeBuild
- AWS CloudFormation
- Amazon RDS PostgreSQL
- AWS Secrets Manager
- Amazon S3
- Amazon Bedrock
- Amazon OpenSearch Serverless
- Amazon CloudWatch

CloudFormation starter infrastructure is available in:

- `infra/cloudformation/`

See `docs/CLOUDFORMATION_AWS_SETUP.md` for setup steps.
For the existing AWS deployment, use the safer pipeline-only template:

- `infra/cloudformation/codepipeline-existing-resources.yml`
- `infra/cloudformation/codepipeline-existing-parameters.example.json`
- `docs/AWS_CLOUDFORMATION_CICD.md`

AWS resource names follow this pattern:

```text
{environment}-dstrmaysam-{project-name}-{resource}
```

Example:

```text
dev-dstrmaysam-stock-market-agent-cluster
dev-dstrmaysam-stock-market-agent-postgres
```

All CloudFormation-created resources include the required capstone tag:

```text
dstrmaysam=dstrmaysam
```

RDS PostgreSQL is private/internal only. ECS can reach RDS on port `5432`;
users cannot connect to the database directly.

### Current AWS deployment

The Streamlit client is deployed on ECS Fargate:

```text
http://3.10.228.209:8501
```

The app connects to the AWS-hosted shared MCP Tools server:

```text
http://16.60.156.10:8000/sse
```

Current AWS resources:

```text
ECR repo: dev-dstrmaysam-stock-market-agent-repo
ECS cluster: dev-dstrmaysam-stock-market-agent-cluster
ECS service: dev-dstrmaysam-stock-market-agent-service
Task definition: dev-dstrmaysam-stock-market-agent-task
CloudWatch log group: /ecs/dev-dstrmaysam-stock-market-agent
```

Note: these URLs use public ECS task IPs. If a task restarts, the IP may change.
For a stable production URL, place the ECS services behind an Application Load
Balancer or API Gateway/custom domain.

## Local run

### Option 1: run backend and frontend separately

Terminal 1 - FastAPI backend:

```bash
uv sync
copy .env.example .env
uv run uvicorn stock_market_agent.api:app --host 0.0.0.0 --port 8002 --reload
```

Terminal 2 - Streamlit frontend:

```bash
set API_BASE_URL=http://localhost:8002
uv run streamlit run streamlit_frontend.py --server.port 8502
```

FastAPI endpoints:

```text
GET  http://localhost:8002/health
GET  http://localhost:8002/config
POST http://localhost:8002/research
POST http://localhost:8002/research/upload
POST http://localhost:8002/portfolio/analyze
GET  http://localhost:8002/watchlist/{user_id}
GET  http://localhost:8002/chat/{session_id}
```

Streamlit UI:

```text
http://localhost:8502
```

### Option 2: run with Docker Compose

This starts two containers: one for FastAPI and one for Streamlit.

```bash
docker compose build
docker compose up -d
```

Docker URLs:

```text
FastAPI:   http://localhost:8002/health
Streamlit: http://localhost:8502
```

If your shared MCP server runs locally on port `8001`, Docker uses
`http://host.docker.internal:8001/sse` by default. To point Docker to another
MCP server:

```bash
set DOCKER_MCP_SERVER_URL=http://your-mcp-server/sse
docker compose up -d
```

### Legacy single-process Streamlit app

The older all-in-one Streamlit app is still available while the split version is
being validated:

```bash
uv sync
copy .env.example .env
uv run streamlit run app.py
```

Example questions to test:

```text
Cisco Systems share price
compare Apple and Meta
show my watchlist
analyze my portfolio
should I buy PepsiCo?
suggest me the best stock of this month
```

The local chatbot stores persistent conversation history in:

```text
data/chat_history.sqlite3
```

This file is ignored by Git. For AWS production, replace the local SQLite
history service with RDS PostgreSQL or DynamoDB.

## Test

```bash
uv run pytest
```

## Build Docker image

Split backend/frontend images:

```bash
docker compose build
```

Legacy single Streamlit image:

```bash
docker build -t stock-market-agent .
```
