from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReportStatus:
    state: str
    report_path: Path | None = None


def get_report_status(sql_path: Path) -> ReportStatus:
    """Determine whether a generated query is waiting or has produced a report."""
    xlsx_path = sql_path.with_suffix(".xlsx")
    csv_path = sql_path.with_suffix(".csv")

    if xlsx_path.is_file():
        return ReportStatus(state="finished", report_path=xlsx_path)
    if csv_path.is_file():
        return ReportStatus(state="finished", report_path=csv_path)
    if sql_path.is_file():
        return ReportStatus(state="starting")
    return ReportStatus(state="starting")