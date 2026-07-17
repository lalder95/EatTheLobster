import pathlib

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

from app.core.schema_export_service import SchemaExportService


class _Conn:
    def __init__(self, url: str, database_name: str = "demo", host: str = "localhost") -> None:
        self.url = url
        self.database_name = database_name
        self.host = host


class _MonkeyTarget:
    def __init__(self, engine) -> None:
        self.engine = engine

    def __call__(self, conn):
        return self.engine


def test_build_schema_snapshot_and_export_json(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    parents = Table(
        "parents",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
    )
    Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parents.id")),
    )
    metadata.create_all(engine)

    monkeypatch.setattr(
        "app.core.schema_export_service.get_target_engine",
        lambda conn: engine,
    )

    conn = _Conn(url="sqlite:///:memory:")
    service = SchemaExportService()
    snapshot = service.build_schema_snapshot(conn)

    assert snapshot["database"] == "demo"
    assert snapshot["host"] == "localhost"
    assert {table["name"] for table in snapshot["tables"]} == {"parents", "children"}
    assert any(rel["from_table"] == "children" and rel["to_table"] == "parents" for rel in snapshot["relationships"])

    output = tmp_path / "schema.json"
    result = service.export_to_json(conn, output)
    assert result == output
    assert output.exists()
    assert "parents" in output.read_text(encoding="utf-8")
