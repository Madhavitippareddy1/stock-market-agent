from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import boto3
import psycopg

from stock_market_agent.config import Settings


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str


class ChatHistoryStore(Protocol):
    def add_message(self, session_id: str, role: str, content: str) -> None: ...

    def get_messages(self, session_id: str, limit: int = 50) -> list[ChatMessage]: ...

    def clear_session(self, session_id: str) -> None: ...

    def build_context(self, session_id: str, limit: int = 10) -> str: ...


class ChatHistoryService:
    """Persistent chat history backed by local SQLite.

    This is intentionally small and dependency-free for local development. In
    AWS, this service can later be replaced with RDS PostgreSQL or DynamoDB
    without changing the Streamlit UI.
    """

    def __init__(self, db_path: str | Path = "data/chat_history.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_settings(cls, settings: Settings) -> ChatHistoryStore:
        database_username = settings.database_username
        database_password = settings.database_password
        if settings.database_secret_arn and (not database_username or not database_password):
            try:
                secret = load_database_secret(settings.database_secret_arn, settings.aws_region)
                database_username = database_username or secret.get("username")
                database_password = database_password or secret.get("password")
            except Exception:
                # Local development should not crash when AWS SSO/session credentials expire.
                # If the secret cannot be read, fall back to SQLite chat history.
                database_username = None
                database_password = None

        if settings.database_host and database_username and database_password:
            return PostgresChatHistoryService(
                host=settings.database_host,
                port=settings.database_port,
                dbname=settings.database_name,
                user=database_username,
                password=database_password,
            )
        return cls(settings.chat_history_db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                ON chat_messages(session_id, created_at, id)
                """
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages(session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, created_at),
            )

    def get_messages(self, session_id: str, limit: int = 50) -> list[ChatMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [ChatMessage(role=row[0], content=row[1], created_at=row[2]) for row in rows]

    def clear_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )

    def build_context(self, session_id: str, limit: int = 10) -> str:
        messages = self.get_messages(session_id=session_id, limit=limit)
        if not messages:
            return ""

        lines = [f"{message.role}: {message.content}" for message in messages]
        return "\n".join(lines)


class PostgresChatHistoryService:
    """Persistent chat history backed by RDS PostgreSQL."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: str,
    ) -> None:
        self.connection_kwargs = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password,
            "connect_timeout": 10,
        }
        self._initialize()

    def _connect(self):
        return psycopg.connect(**self.connection_kwargs)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                ON chat_messages(session_id, created_at, id)
                """
            )

    def add_message(self, session_id: str, role: str, content: str) -> None:
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages(session_id, role, content, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, role, content, created_at),
            )

    def get_messages(self, session_id: str, limit: int = 50) -> list[ChatMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at::TEXT
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()

        return [ChatMessage(role=row[0], content=row[1], created_at=row[2]) for row in rows]

    def clear_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = %s",
                (session_id,),
            )

    def build_context(self, session_id: str, limit: int = 10) -> str:
        messages = self.get_messages(session_id=session_id, limit=limit)
        if not messages:
            return ""

        lines = [f"{message.role}: {message.content}" for message in messages]
        return "\n".join(lines)


def load_database_secret(secret_arn: str, region_name: str) -> dict[str, str]:
    client = boto3.client("secretsmanager", region_name=region_name)
    payload = client.get_secret_value(SecretId=secret_arn)
    return json.loads(payload["SecretString"])
