from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chatbot_app.config import METADATA_DB_PATH, _ensure_dirs
from chatbot_app.data.models import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _ensure_dirs()
        _engine = create_engine(
            f"sqlite:///{METADATA_DB_PATH}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False
        )
    return _SessionLocal()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
