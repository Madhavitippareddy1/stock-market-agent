from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "stock-market-agent"
    environment: str = "local"

    aws_region: str = "eu-west-2"
    reports_bucket: str | None = None
    opensearch_endpoint: str | None = None
    opensearch_index: str = "financial-report-chunks"

    database_host: str | None = None
    database_port: int = 5432
    database_name: str = "stockagent"
    database_username: str | None = None
    database_password: str | None = None
    database_secret_arn: str | None = None
    chat_history_db_path: str = "data/chat_history.sqlite3"

    mcp_server_url: str | None = "http://localhost:8001/sse"
    mcp_api_key: str | None = None

    bedrock_chat_model_id: str = "amazon.nova-lite-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_flush_on_request: bool = False

    ragas_enabled: bool = True
    ragas_score_prefix: str = "ragas"
    ragas_min_context_precision: float = 0.45
    ragas_min_faithfulness: float = 0.55


def get_settings() -> Settings:
    return Settings()
