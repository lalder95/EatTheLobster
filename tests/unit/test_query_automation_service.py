import pathlib

import pandas as pd
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.query_automation_service import QueryAutomationService
from app.data.models import Base, DbConnection, QueryAutomationSettings, QueryRun


@pytest.fixture()
def service():
    return QueryAutomationService()


@pytest.fixture()
def metadata_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _configure_metadata(factory, folder: pathlib.Path, conn_id: int = 1):
    session = factory()
    connection = DbConnection(
        id=conn_id,
        name="Primary",
        host="localhost",
        port=3306,
        database_name="demo",
        username="user",
        encrypted_password="secret",
    )
    settings = QueryAutomationSettings(
        query_folder_path=str(folder),
        default_db_connection_id=conn_id,
        archive_folder_name="archive",
        enabled=True,
    )
    session.add(connection)
    session.add(settings)
    session.commit()
    session.close()


def test_scan_once_executes_query_and_archives_file(
    service, metadata_session_factory, monkeypatch, tmp_path
):
    folder = tmp_path / "queries"
    folder.mkdir()
    sql_file = folder / "people.sql"
    sql_file.write_text("select id, name from people order by id", encoding="utf-8")

    target_engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    people = Table(
        "people",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
    )
    metadata.create_all(target_engine)
    with target_engine.begin() as conn:
        conn.execute(
            people.insert(),
            [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        )

    _configure_metadata(metadata_session_factory, folder)
    monkeypatch.setattr(
        "app.core.query_automation_service.get_session",
        metadata_session_factory,
    )
    monkeypatch.setattr(
        "app.core.query_automation_service.get_target_engine",
        lambda _conn: target_engine,
    )

    processed = service.scan_once(trigger_type="manual")

    assert processed == 1
    output_file = folder / "people.xlsx"
    assert output_file.exists()
    assert not sql_file.exists()
    assert (folder / "archive" / "people.sql").exists()

    session = metadata_session_factory()
    try:
        runs = session.query(QueryRun).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "success"
        assert run.row_count == 2
        assert run.output_file_path.endswith("people.xlsx")
        assert run.archived_file_path.endswith("people.sql")
    finally:
        session.close()


def test_scan_once_falls_back_to_csv_when_excel_write_fails(
    service, metadata_session_factory, monkeypatch, tmp_path
):
    folder = tmp_path / "queries"
    folder.mkdir()
    sql_file = folder / "items.sql"
    sql_file.write_text("select 1 as value", encoding="utf-8")

    target_engine = create_engine("sqlite:///:memory:")
    _configure_metadata(metadata_session_factory, folder)
    monkeypatch.setattr(
        "app.core.query_automation_service.get_session",
        metadata_session_factory,
    )
    monkeypatch.setattr(
        "app.core.query_automation_service.get_target_engine",
        lambda _conn: target_engine,
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("no excel")

    monkeypatch.setattr(pd.DataFrame, "to_excel", _raise)

    processed = service.scan_once(trigger_type="manual")

    assert processed == 1
    assert (folder / "items.csv").exists()
    assert not (folder / "items.xlsx").exists()
    assert (folder / "archive" / "items.sql").exists()


def test_second_scan_skips_archived_files(
    service, metadata_session_factory, monkeypatch, tmp_path
):
    folder = tmp_path / "queries"
    folder.mkdir()
    sql_file = folder / "orders.sql"
    sql_file.write_text("select 1 as value", encoding="utf-8")

    target_engine = create_engine("sqlite:///:memory:")
    _configure_metadata(metadata_session_factory, folder)
    monkeypatch.setattr(
        "app.core.query_automation_service.get_session",
        metadata_session_factory,
    )
    monkeypatch.setattr(
        "app.core.query_automation_service.get_target_engine",
        lambda _conn: target_engine,
    )

    first = service.scan_once(trigger_type="manual")
    second = service.scan_once(trigger_type="manual")

    assert first == 1
    assert second == 0
    session = metadata_session_factory()
    try:
        assert session.query(QueryRun).count() == 1
    finally:
        session.close()


def test_scan_once_strips_markdown_and_go_batches(
    service, metadata_session_factory, monkeypatch, tmp_path
):
    folder = tmp_path / "queries"
    folder.mkdir()
    sql_file = folder / "fenced.sql"
    sql_file.write_text(
        """Here is the report query:
```sql
create table temp_results (value integer);
GO
insert into temp_results (value) values (42);
GO
select value from temp_results;
```
""",
        encoding="utf-8",
    )

    target_engine = create_engine("sqlite:///:memory:")
    _configure_metadata(metadata_session_factory, folder)
    monkeypatch.setattr(
        "app.core.query_automation_service.get_session",
        metadata_session_factory,
    )
    monkeypatch.setattr(
        "app.core.query_automation_service.get_target_engine",
        lambda _conn: target_engine,
    )

    processed = service.scan_once(trigger_type="manual")

    assert processed == 1
    assert (folder / "fenced.xlsx").exists()
    assert (folder / "archive" / "fenced.sql").exists()