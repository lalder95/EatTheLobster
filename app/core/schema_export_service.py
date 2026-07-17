import json
import pathlib
from typing import Any

from sqlalchemy import inspect

from app.data.database import get_target_engine


class SchemaExportService:
    def build_schema_snapshot(self, conn) -> dict[str, Any]:
        engine = get_target_engine(conn)
        inspector = inspect(engine)

        tables: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for table_name in inspector.get_table_names():
            columns: list[dict[str, Any]] = []
            for column in inspector.get_columns(table_name):
                columns.append(
                    {
                        "name": column.get("name"),
                        "type": str(column.get("type")),
                        "nullable": bool(column.get("nullable", True)),
                        "default": column.get("default"),
                        "autoincrement": column.get("autoincrement"),
                    }
                )

            tables.append(
                {
                    "name": table_name,
                    "columns": columns,
                    "primary_key": list(inspector.get_pk_constraint(table_name).get("constrained_columns", [])),
                }
            )

            for fk in inspector.get_foreign_keys(table_name):
                relationships.append(
                    {
                        "from_table": table_name,
                        "from_columns": list(fk.get("constrained_columns", [])),
                        "to_table": fk.get("referred_table"),
                        "to_columns": list(fk.get("referred_columns", [])),
                        "name": fk.get("name"),
                        "options": fk.get("options", {}),
                    }
                )

        return {
            "database": conn.database_name,
            "host": conn.host,
            "tables": tables,
            "relationships": relationships,
        }

    def export_to_json(self, conn, output_path: str | pathlib.Path) -> pathlib.Path:
        snapshot = self.build_schema_snapshot(conn)
        path = pathlib.Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        return path