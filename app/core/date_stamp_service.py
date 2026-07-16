import datetime
import pathlib
import re
from typing import Union

import pandas as pd
from sqlalchemy import Engine, inspect, text
import logging

logger = logging.getLogger(__name__)

_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def _validate_identifier(name: str) -> None:
    if not _VALID_IDENTIFIER.match(name):
        raise ValueError(f"Invalid SQL identifier: '{name}'")


class DateStampService:
    def get_file_created_time(
        self, file_path: Union[str, pathlib.Path]
    ) -> datetime.datetime:
        path = pathlib.Path(file_path)
        stat = path.stat()
        # st_birthtime is Windows/macOS creation time; fall back to st_mtime
        ts = getattr(stat, "st_birthtime", None) or stat.st_mtime
        return datetime.datetime.fromtimestamp(ts)

    def apply_timestamp(
        self,
        df: pd.DataFrame,
        column_name: str,
        timestamp: datetime.datetime,
    ) -> pd.DataFrame:
        df = df.copy()
        df[column_name] = timestamp
        return df

    def ensure_timestamp_column(
        self, engine: Engine, table_name: str, column_name: str
    ) -> None:
        _validate_identifier(table_name)
        _validate_identifier(column_name)

        insp = inspect(engine)
        if not insp.has_table(table_name):
            # Table will be created by to_sql; column is already in DataFrame
            return

        existing = [c["name"] for c in insp.get_columns(table_name)]
        if column_name not in existing:
            from app.data.database import quote_name
            with engine.connect() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {quote_name(engine, table_name)} "
                        f"ADD {quote_name(engine, column_name)} DATETIME NULL"
                    )
                )
                conn.commit()
            logger.info(
                f"Added column '{column_name}' to table '{table_name}'"
            )
