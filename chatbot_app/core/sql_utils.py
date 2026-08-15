from __future__ import annotations

import datetime
import getpass
import re
from pathlib import Path

SQL_START_RE = re.compile(r"^(with|select|insert|update|delete|merge|create|alter|drop|truncate)\b", re.IGNORECASE)
SQL_FENCE_RE = re.compile(r"```\s*(?:sql|tsql|mysql)?\s*\r?\n(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def extract_sql_text(response_text: str) -> str:
    text = response_text.strip()
    fenced = SQL_FENCE_RE.search(text)
    if fenced is not None:
        text = fenced.group(1).strip()
    if text.lower().startswith("sql\n"):
        text = text[4:].strip()
    return _strip_leading_sql_noise(text.strip())


def extract_final_sql(response_text: str) -> str | None:
    """Return SQL only when the assistant explicitly produced a final SQL response."""
    fenced = SQL_FENCE_RE.search(response_text)
    if fenced is not None:
        sql_text = _strip_leading_sql_noise(fenced.group(1).strip())
        return sql_text if is_sql_text(sql_text) else None

    sql_text = _strip_leading_sql_noise(response_text.strip())
    return sql_text if is_sql_text(sql_text) else None


def is_sql_text(sql_text: str) -> bool:
    return bool(SQL_START_RE.match(_strip_leading_sql_noise(sql_text.strip())))


def sanitize_filename_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return cleaned or "user"


def build_sql_output_path(output_folder: Path, username: str | None = None) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    safe_user = sanitize_filename_component(username or getpass.getuser())
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_folder / f"report_{safe_user}_{timestamp}.sql"


def _strip_leading_sql_noise(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and lines[0].lstrip().startswith("--"):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    if lines and lines[0].lstrip().startswith("/*"):
        while lines:
            line = lines.pop(0)
            if "*/" in line:
                break
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()
