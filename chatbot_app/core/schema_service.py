from __future__ import annotations

import json
from pathlib import Path

from chatbot_app.config import SCHEMA_SOURCE_PATH


def load_schema_context(schema_path: Path = SCHEMA_SOURCE_PATH) -> str:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    raw = schema_path.read_text(encoding="utf-8-sig")
    parsed = json.loads(raw)
    lines: list[str] = [f"Schema source: {schema_path}"]
    _summarize_node(parsed, lines, indent="")
    return "\n".join(lines)


def _summarize_node(node, lines: list[str], indent: str) -> None:
    if isinstance(node, dict):
        table_list = node.get("tables")
        if isinstance(table_list, list):
            database_name = node.get("database") or node.get("database_name")
            if database_name:
                lines.append(f"{indent}Database: {database_name}")
            for table in table_list:
                if isinstance(table, dict):
                    table_name = table.get("name") or table.get("table_name") or "unknown_table"
                    lines.append(f"{indent}Table: {table_name}")
                    columns = table.get("columns")
                    if isinstance(columns, list):
                        for column in columns:
                            if isinstance(column, dict):
                                column_name = column.get("name") or column.get("column_name") or "unknown_column"
                                column_type = column.get("type") or column.get("data_type") or "unknown"
                                lines.append(f"{indent}  - {column_name}: {column_type}")
                            else:
                                lines.append(f"{indent}  - {column}")
                    elif isinstance(columns, dict):
                        for column_name, column_info in columns.items():
                            if isinstance(column_info, dict):
                                column_type = column_info.get("type") or column_info.get("data_type") or "unknown"
                            else:
                                column_type = str(column_info)
                            lines.append(f"{indent}  - {column_name}: {column_type}")
                else:
                    lines.append(f"{indent}Table: {table}")
            return

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{indent}{key}:")
                _summarize_node(value, lines, indent + "  ")
            else:
                lines.append(f"{indent}{key}: {value}")
        return

    if isinstance(node, list):
        for item in node:
            _summarize_node(item, lines, indent)
        return

    lines.append(f"{indent}{node}")
