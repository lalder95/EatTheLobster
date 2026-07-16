from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from app.config import METADATA_DB_PATH, _ensure_dirs
from app.data.models import Base

if TYPE_CHECKING:
    from app.data.models import DbConnection

_engine: Engine | None = None
_SessionLocal = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _ensure_dirs()
        _engine = create_engine(
            f"sqlite:///{METADATA_DB_PATH}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal()


def _migrate_db_connections() -> None:
    """Add columns to db_connections introduced after initial deployment."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(db_connections)")).fetchall()
        existing = {row[1] for row in rows}
        migrations = [
            ("db_type", "VARCHAR(16) NOT NULL DEFAULT 'mysql'"),
            ("use_windows_auth", "BOOLEAN NOT NULL DEFAULT 0"),
            ("instance_name", "VARCHAR(128) NULL"),
        ]
        for col_name, col_def in migrations:
            if col_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE db_connections ADD COLUMN {col_name} {col_def}")
                )
        conn.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
    _migrate_db_connections()


def quote_name(engine: Engine, name: str) -> str:
    """Return a properly quoted SQL identifier for the engine's dialect."""
    return engine.dialect.identifier_preparer.quote(name)


def get_target_engine(conn: "DbConnection") -> Engine:
    """Build and return a SQLAlchemy engine for the given DbConnection."""
    db_type = getattr(conn, "db_type", None) or "mysql"

    if db_type == "mssql":
        from app.config import decrypt

        driver = "ODBC Driver 18 for SQL Server"
        instance_name = getattr(conn, "instance_name", None) or ""
        server = (
            f"{conn.host}\\{instance_name}" if instance_name
            else f"{conn.host},{conn.port}"
        )
        parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={conn.database_name}",
            "TrustServerCertificate=yes",
        ]
        use_windows_auth = getattr(conn, "use_windows_auth", False)
        if use_windows_auth:
            parts.append("Trusted_Connection=yes")
        else:
            password = decrypt(conn.encrypted_password)
            parts += [f"UID={conn.username}", f"PWD={password}"]

        odbc_str = ";".join(parts)
        url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"
        return create_engine(url, pool_pre_ping=True, fast_executemany=True)

    # MySQL (default)
    from app.config import decrypt

    password = decrypt(conn.encrypted_password)
    url = URL.create(
        "mysql+pymysql",
        username=conn.username,
        password=password,
        host=conn.host,
        port=conn.port,
        database=conn.database_name,
    )
    return create_engine(url, pool_pre_ping=True)


def get_mysql_engine(conn: "DbConnection") -> Engine:
    """Deprecated alias for get_target_engine()."""
    return get_target_engine(conn)
