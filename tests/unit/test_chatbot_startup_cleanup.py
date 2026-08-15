from types import SimpleNamespace

from chatbot_app import main as chatbot_main


class _Session:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_startup_cleanup_uses_query_automation_archive_settings(monkeypatch, tmp_path):
    session = _Session()
    settings = SimpleNamespace(
        query_folder_path=str(tmp_path),
        archive_folder_name="archive",
    )
    cleanup_calls = []

    class _SettingsRepository:
        def __init__(self, repository_session) -> None:
            assert repository_session is session

        def get(self):
            return settings

    class _CleanupService:
        def cleanup(self, **kwargs):
            cleanup_calls.append(kwargs)
            return [tmp_path / "archive" / "old.sql"]

        def cleanup_report_outputs(self, **kwargs):
            cleanup_calls.append(kwargs)
            return [tmp_path / "old.xlsx"]

    monkeypatch.setattr(chatbot_main, "init_query_automation_db", lambda: None)
    monkeypatch.setattr(chatbot_main, "get_query_automation_session", lambda: session)
    monkeypatch.setattr(chatbot_main, "QueryAutomationSettingsRepository", _SettingsRepository)
    monkeypatch.setattr(chatbot_main, "SqlArchiveCleanupService", _CleanupService)

    deleted = chatbot_main.cleanup_sql_archive_on_startup()

    assert deleted == 2
    assert session.closed is True
    assert cleanup_calls == [
        {
            "query_folder": str(tmp_path),
            "archive_folder_name": "archive",
            "retention_days": 90,
        },
        {
            "query_folder": str(tmp_path),
            "retention_days": 90,
        },
    ]


def test_startup_cleanup_skips_when_query_folder_is_not_configured(monkeypatch):
    session = _Session()
    settings = SimpleNamespace(query_folder_path="", archive_folder_name="archive")

    class _SettingsRepository:
        def __init__(self, repository_session) -> None:
            assert repository_session is session

        def get(self):
            return settings

    monkeypatch.setattr(chatbot_main, "init_query_automation_db", lambda: None)
    monkeypatch.setattr(chatbot_main, "get_query_automation_session", lambda: session)
    monkeypatch.setattr(chatbot_main, "QueryAutomationSettingsRepository", _SettingsRepository)

    assert chatbot_main.cleanup_sql_archive_on_startup() == 0
    assert session.closed is True