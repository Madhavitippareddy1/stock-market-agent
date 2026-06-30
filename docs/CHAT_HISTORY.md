# Chatbot and Persistent History

The Streamlit app includes a chatbot interface in the `Agent Research` tab.

## Local storage

Chat history is stored locally in SQLite:

```text
data/chat_history.sqlite3
```

The service is implemented in:

```text
src/stock_market_agent/services/chat_history.py
```

## AWS storage

When these environment variables are available, the same service automatically
uses RDS PostgreSQL instead of SQLite:

```text
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USERNAME
DATABASE_PASSWORD
```

CloudFormation creates the RDS PostgreSQL database and passes these values to
the ECS task.

## What is saved

Each message stores:

- Session ID
- Role: `user` or `assistant`
- Message content
- Created timestamp

## How it is used

Before each new question, the app loads recent chat history and includes it as
conversation context for LangGraph routing.

```text
Streamlit chat input
  -> ChatHistoryService
  -> LangGraphSupervisor
  -> Specialist agent
  -> MCP tools / Bedrock
  -> Assistant response saved to history
```

## Production table

```text
chat_messages
  id
  user_id
  session_id
  role
  content
  created_at
```
