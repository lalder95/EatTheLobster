import json
import pathlib
from typing import Any

from sqlalchemy import inspect

from app.data.database import get_target_engine


class SchemaExportService:
    _TEXT_TYPE_MARKERS = ("char", "text", "clob")
    _DATE_TYPE_MARKERS = ("date", "time")
    _DECIMAL_TYPE_MARKERS = (
        "decimal",
        "numeric",
        "money",
        "real",
        "float",
        "double",
    )
    _INTEGER_TYPE_MARKERS = ("int", "serial")
    _CURRENCY_NAME_MARKERS = (
        "amount",
        "balance",
        "cost",
        "margin",
        "price",
        "revenue",
        "sale",
        "sales",
        "total",
    )
    _PERCENTAGE_NAME_MARKERS = ("percent", "percentage", "pct", "rate")
    _DATE_NAME_MARKERS = ("date", "_at", "timestamp", "time")
    _IDENTIFIER_NAME_MARKERS = ("_id", "code", "number", "sku")

    def build_schema_snapshot(self, conn) -> dict[str, Any]:
        engine = get_target_engine(conn)
        inspector = inspect(engine)

        tables: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for table_name in inspector.get_table_names():
            columns: list[dict[str, Any]] = []
            for column in inspector.get_columns(table_name):
                column_name = column.get("name")
                storage_type = str(column.get("type"))
                columns.append(
                    {
                        "name": column_name,
                        "type": storage_type,
                        "nullable": bool(column.get("nullable", True)),
                        "default": column.get("default"),
                        "autoincrement": column.get("autoincrement"),
                        **self._build_format_metadata(column_name, storage_type),
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
            "schema_format_version": 2,
            "database": conn.database_name,
            "host": conn.host,
            "tables": tables,
            "relationships": relationships,
        }

    def _build_format_metadata(
        self,
        column_name: str | None,
        storage_type: str,
    ) -> dict[str, Any]:
        """Infer report-friendly field metadata without inspecting source values."""
        name = (column_name or "").lower()
        type_name = (storage_type or "").lower()
        is_text = any(marker in type_name for marker in self._TEXT_TYPE_MARKERS)
        is_native_date = any(
            marker in type_name for marker in self._DATE_TYPE_MARKERS
        )
        is_decimal = any(
            marker in type_name for marker in self._DECIMAL_TYPE_MARKERS
        )
        is_integer = any(
            marker in type_name for marker in self._INTEGER_TYPE_MARKERS
        ) and not is_decimal
        is_currency_name = any(
            marker in name for marker in self._CURRENCY_NAME_MARKERS
        )
        is_percentage_name = any(
            marker in name for marker in self._PERCENTAGE_NAME_MARKERS
        )
        is_date_name = any(marker in name for marker in self._DATE_NAME_MARKERS)
        is_identifier_name = any(
            marker in name for marker in self._IDENTIFIER_NAME_MARKERS
        )

        metadata: dict[str, Any] = {
            "logical_type": "text",
            "format_hint": "text",
            "is_aggregate_safe": False,
            "is_date_filter_safe": is_native_date,
            "sql_conversion_hint": None,
        }

        if is_native_date:
            metadata.update(
                logical_type="datetime" if "time" in type_name else "date",
                format_hint="ISO date/time",
                is_date_filter_safe=True,
            )
        elif is_date_name and is_text:
            metadata.update(
                logical_type="date",
                format_hint="MM/dd/yyyy date stored as text",
                is_date_filter_safe=False,
                sql_conversion_hint=(
                    "TRY_CONVERT(date, "
                    f"LTRIM(RTRIM([{column_name}])), 101)"
                ),
            )
        elif is_percentage_name and (is_text or is_decimal or is_integer):
            metadata.update(
                logical_type="percentage",
                format_hint="percentage",
                is_aggregate_safe=not is_text,
                sql_conversion_hint=(
                    self._numeric_conversion_hint(column_name) if is_text else None
                ),
            )
        elif is_currency_name and (is_text or is_decimal or is_integer):
            metadata.update(
                logical_type="currency",
                format_hint="currency with two decimal places",
                is_aggregate_safe=not is_text,
                sql_conversion_hint=(
                    self._numeric_conversion_hint(column_name) if is_text else None
                ),
            )
        elif is_decimal:
            metadata.update(
                logical_type="decimal",
                format_hint="decimal number",
                is_aggregate_safe=True,
            )
        elif is_integer and not is_identifier_name:
            metadata.update(
                logical_type="integer",
                format_hint="whole number",
                is_aggregate_safe=True,
            )
        elif is_identifier_name:
            metadata.update(
                logical_type="identifier",
                format_hint="identifier; preserve as text",
            )

        return metadata

    @staticmethod
    def _numeric_conversion_hint(column_name: str | None) -> str:
        return (
            "TRY_CONVERT(decimal(18,2), "
            f"REPLACE(NULLIF(LTRIM(RTRIM([{column_name}])), ''), ',', ''))"
        )

    def export_to_json(self, conn, output_path: str | pathlib.Path) -> pathlib.Path:
        snapshot = self.build_schema_snapshot(conn)
        path = pathlib.Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
        return path