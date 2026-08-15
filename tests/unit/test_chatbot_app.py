from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chatbot_app.core.chatbot_service import ChatbotService
from chatbot_app.core.report_status_service import get_report_status
from chatbot_app.core.schema_service import load_schema_context
from chatbot_app.core.sql_utils import (
    build_sql_output_path,
    extract_final_sql,
    extract_sql_text,
    is_sql_text,
)
from chatbot_app.data.models import Base
from chatbot_app.data.repositories import (
    ChatbotConversationRepository,
    ChatbotMessageRepository,
    ChatbotSettingsRepository,
)


def test_extract_sql_text_strips_code_fence() -> None:
    text = """Here is the query:

```sql
SELECT * FROM customers;
```
"""

    sql_text = extract_sql_text(text)

    assert sql_text == "SELECT * FROM customers;"
    assert is_sql_text(sql_text)


def test_extract_sql_text_strips_leading_comments() -> None:
    text = """-- explanation

/* ignore this */

SELECT 1;
"""

    sql_text = extract_sql_text(text)

    assert sql_text == "SELECT 1;"
    assert is_sql_text(sql_text)


def test_extract_final_sql_requires_explicit_sql_response() -> None:
    assert extract_final_sql("What date range should the report cover?") is None
    assert extract_final_sql("```sql\nSELECT 1;\n```") == "SELECT 1;"
    assert extract_final_sql("Here is the final query:\n```\nSELECT 1;\n```") == "SELECT 1;"


def test_build_sql_output_path_uses_username(tmp_path: Path) -> None:
    output_path = build_sql_output_path(tmp_path, username="Lucas Test")

    assert output_path.parent == tmp_path
    assert output_path.name.startswith("report_Lucas_Test_")
    assert output_path.suffix == ".sql"


def test_report_status_is_starting_while_sql_file_exists(tmp_path: Path) -> None:
    sql_file = tmp_path / "report_Lucas_20260815_120000.sql"
    sql_file.write_text("SELECT 1;", encoding="utf-8")

    status = get_report_status(sql_file)

    assert status.state == "starting"
    assert status.report_path is None


def test_report_status_is_finished_when_matching_report_exists(tmp_path: Path) -> None:
    sql_file = tmp_path / "report_Lucas_20260815_120000.sql"
    report_file = sql_file.with_suffix(".xlsx")
    report_file.write_bytes(b"report")

    status = get_report_status(sql_file)

    assert status.state == "finished"
    assert status.report_path == report_file


def test_schema_loader_summarizes_tables(tmp_path: Path) -> None:
    schema_file = tmp_path / "db_schema.json"
    schema_file.write_text(
        """
        {
            "database": "demo",
            "tables": [
                {
                    "name": "customers",
                    "columns": [
                        {"name": "id", "type": "int"},
                        {"name": "name", "type": "varchar"}
                    ]
                }
            ]
        }
        """,
        encoding="utf-8",
    )

    context = load_schema_context(schema_file)

    assert "Schema source:" in context
    assert "Database: demo" in context
    assert "Table: customers" in context
    assert "id: int" in context


def test_schema_context_includes_field_format_metadata(tmp_path: Path) -> None:
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(
                """
                {
                    "database": "demo",
                    "tables": [
                        {
                            "name": "salesDetail",
                            "columns": [
                                {
                                    "name": "net_sales",
                                    "type": "NVARCHAR(max)",
                                    "logical_type": "currency",
                                    "format_hint": "currency with two decimal places",
                                    "is_aggregate_safe": false,
                                    "is_date_filter_safe": false,
                                    "sql_conversion_hint": "TRY_CONVERT(decimal(18,2), [net_sales])"
                                }
                            ]
                        }
                    ]
                }
                """,
                encoding="utf-8",
        )

        context = load_schema_context(schema_file)

        assert "logical type=currency" in context
        assert "aggregate-safe=False" in context
        assert "SQL Server conversion=TRY_CONVERT(decimal(18,2), [net_sales])" in context


def test_chatbot_prompt_requires_plain_language() -> None:
    prompt = ChatbotService()._build_system_prompt("schema context")

    assert "not technical" in prompt
    assert "one simple question at a time" in prompt
    assert "aggregate by store" in prompt
    assert "sort from highest to lowest" in prompt
    assert "TRY_CONVERT(decimal(18,2)" in prompt
    assert "TRY_CONVERT(date" in prompt


def test_settings_repository_roundtrip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()

    try:
        repo = ChatbotSettingsRepository(session)
        settings = repo.get()
        assert settings.model_name == "gpt-4o-mini"

        updated = repo.save(
            output_folder_path="C:/reports",
            model_name="gpt-4.1-mini",
            enabled=False,
        )

        assert updated.output_folder_path == "C:/reports"
        assert updated.model_name == "gpt-4.1-mini"
        assert updated.enabled is False
    finally:
        session.close()


def test_conversation_repository_roundtrip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()

    try:
        convo_repo = ChatbotConversationRepository(session)
        msg_repo = ChatbotMessageRepository(session)
        conversation = convo_repo.create(
            title="Quarterly sales",
            model_name="gpt-4o-mini",
            output_folder_path="C:/reports",
            schema_source_path="\\\\server\\schema.json",
        )
        msg_repo.add_message(conversation.id, "user", "Build a report")
        msg_repo.add_message(conversation.id, "assistant", "SELECT 1;")

        loaded = convo_repo.get_most_recent()
        assert loaded is not None
        assert loaded.title == "Quarterly sales"
        messages = msg_repo.get_for_conversation(loaded.id)
        assert [message.role for message in messages] == ["user", "assistant"]
    finally:
        session.close()


def test_chatbot_service_generates_and_saves_sql(tmp_path: Path, monkeypatch) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="```sql\nSELECT 1;\n```")
                    )
                ]
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.get_openai_api_key",
        lambda: "secret-key",
    )
    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.load_schema_context",
        lambda _schema_path=None: "schema context",
    )
    monkeypatch.setattr("chatbot_app.core.chatbot_service.OpenAI", FakeClient)
    output_path = tmp_path / "report_Lucas_20260101_010101.sql"
    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.build_sql_output_path",
        lambda _folder, username=None: output_path,
    )

    service = ChatbotService()
    result = service.generate_sql(
        user_message="Create a simple report",
        history=[],
        model_name="gpt-4o-mini",
        output_folder=tmp_path,
    )

    assert result.sql_text == "SELECT 1;"
    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "SELECT 1;\n"


def test_chatbot_service_reports_file_save_failure(tmp_path: Path, monkeypatch) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="```sql\nSELECT 1;\n```"))
                ]
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("chatbot_app.core.chatbot_service.get_openai_api_key", lambda: "secret-key")
    monkeypatch.setattr("chatbot_app.core.chatbot_service.load_schema_context", lambda _schema_path=None: "schema context")
    monkeypatch.setattr("chatbot_app.core.chatbot_service.OpenAI", FakeClient)
    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.build_sql_output_path",
        lambda _folder: tmp_path / "missing" / "query.sql",
    )

    service = ChatbotService()

    try:
        service.generate_sql("Create a report", [], "gpt-4o-mini", tmp_path)
        raise AssertionError("Expected SqlSaveError")
    except Exception as exc:
        from chatbot_app.core.chatbot_service import SqlSaveError

        assert isinstance(exc, SqlSaveError)


def test_chatbot_service_returns_conversation_response_without_saving_sql(tmp_path: Path, monkeypatch) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Here is a suggestion, not SQL.")
                    )
                ]
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.get_openai_api_key",
        lambda: "secret-key",
    )
    monkeypatch.setattr(
        "chatbot_app.core.chatbot_service.load_schema_context",
        lambda _schema_path=None: "schema context",
    )
    monkeypatch.setattr("chatbot_app.core.chatbot_service.OpenAI", FakeClient)

    service = ChatbotService()

    result = service.generate_sql(
        user_message="Create a simple report",
        history=[],
        model_name="gpt-4o-mini",
        output_folder=tmp_path,
    )

    assert result.assistant_text == "Here is a suggestion, not SQL."
    assert result.sql_text is None
    assert result.output_path is None
