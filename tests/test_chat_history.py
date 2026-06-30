from stock_market_agent.services.chat_history import ChatHistoryService


def test_chat_history_persists_messages(tmp_path):
    db_path = tmp_path / "chat.sqlite3"
    service = ChatHistoryService(db_path)

    service.add_message("session-1", "user", "Cisco price?")
    service.add_message("session-1", "assistant", "CSCO is available.")

    reloaded = ChatHistoryService(db_path)
    messages = reloaded.get_messages("session-1")

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Cisco price?"


def test_chat_history_clear_session(tmp_path):
    service = ChatHistoryService(tmp_path / "chat.sqlite3")
    service.add_message("session-1", "user", "hello")

    service.clear_session("session-1")

    assert service.get_messages("session-1") == []


def test_chat_history_build_context(tmp_path):
    service = ChatHistoryService(tmp_path / "chat.sqlite3")
    service.add_message("session-1", "user", "compare Apple and Meta")
    service.add_message("session-1", "assistant", "Compared AAPL and META")

    context = service.build_context("session-1")

    assert "user: compare Apple and Meta" in context
    assert "assistant: Compared AAPL and META" in context
