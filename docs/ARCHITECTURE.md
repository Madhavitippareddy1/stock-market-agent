# Stock Market Agent Architecture

## Application flow

```text
End User
  -> Streamlit UI
  -> Supervisor Agent
  -> Stock Agent / RAG Agent / User Agent / Portfolio Agent
  -> Shared MCP Server
  -> AWS + market data + database tools
```

## Why shared MCP

The MCP server is common for five projects, so this project should not own the
tool implementation directly. This project only calls tools through the shared
MCP interface.

Benefits:

- One common tool layer for all projects.
- Easier reuse of stock, RAG, user, and portfolio tools.
- Cleaner agent code.
- Better security because AWS/database access is centralized.

## AWS services

- ECS Fargate: runs Streamlit container.
- ECR: stores Docker images.
- CodePipeline: deployment pipeline.
- CodeBuild: tests, builds, and pushes image.
- S3: financial reports and build artifacts.
- Bedrock: LLM and embeddings.
- OpenSearch Serverless: vector search.
- CloudWatch: logs and alarms.
