import datetime
import json

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class DbConnection(Base):
    __tablename__ = "db_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    host = Column(String(256), nullable=False)
    port = Column(Integer, nullable=False, default=3306)
    database_name = Column(String(128), nullable=False)
    username = Column(String(128), nullable=False)
    encrypted_password = Column(Text, nullable=False)
    db_type = Column(String(16), nullable=False, default="mysql")
    use_windows_auth = Column(Boolean, nullable=False, default=False)
    instance_name = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    jobs = relationship(
        "ImportJob", back_populates="db_connection", cascade="all, delete-orphan"
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    # 'file' or 'directory'
    source_type = Column(String(16), nullable=False)
    source_path = Column(Text, nullable=False)
    db_connection_id = Column(
        Integer, ForeignKey("db_connections.id"), nullable=False
    )
    target_table = Column(String(128), nullable=False)
    # True = append rows; False = truncate then import
    append_mode = Column(Boolean, nullable=False, default=True)
    use_file_created_date = Column(Boolean, nullable=False, default=False)
    # Target column name to receive the file-created timestamp
    file_created_date_column = Column(String(128), nullable=True)
    ignore_previously_imported = Column(Boolean, nullable=False, default=True)
    # 'interval', 'daily', 'weekly'
    frequency_type = Column(String(32), nullable=False)
    # JSON: {"minutes": 30} | {"time": "08:00"} | {"weekday": 0, "time": "08:00"}
    frequency_config = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    db_connection = relationship("DbConnection", back_populates="jobs")
    column_mappings = relationship(
        "ColumnMapping", back_populates="job", cascade="all, delete-orphan"
    )
    runs = relationship(
        "ImportRun", back_populates="job", cascade="all, delete-orphan"
    )
    imported_files = relationship(
        "ImportedFile", back_populates="job", cascade="all, delete-orphan"
    )

    @property
    def frequency_config_dict(self) -> dict:
        return json.loads(self.frequency_config)


class ColumnMapping(Base):
    __tablename__ = "column_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=False)
    source_column = Column(String(256), nullable=False)
    target_column = Column(String(256), nullable=False)

    job = relationship("ImportJob", back_populates="column_mappings")


class ImportRun(Base):
    __tablename__ = "import_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=False)
    started_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    completed_at = Column(DateTime, nullable=True)
    # 'running' | 'success' | 'failed' | 'partial'
    status = Column(String(16), nullable=False, default="running")
    files_processed = Column(Integer, nullable=False, default=0)
    rows_imported = Column(Integer, nullable=False, default=0)
    rows_skipped = Column(Integer, nullable=False, default=0)
    # 'manual' | 'scheduled'
    trigger_type = Column(String(16), nullable=False, default="scheduled")

    job = relationship("ImportJob", back_populates="runs")
    errors = relationship(
        "ImportError", back_populates="run", cascade="all, delete-orphan"
    )
    imported_files = relationship("ImportedFile", back_populates="run")


class ImportError(Base):
    __tablename__ = "import_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("import_runs.id"), nullable=False)
    file_path = Column(Text, nullable=True)
    error_type = Column(String(64), nullable=False)
    error_message = Column(Text, nullable=False)
    occurred_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    run = relationship("ImportRun", back_populates="errors")


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=False)
    run_id = Column(Integer, ForeignKey("import_runs.id"), nullable=True)
    file_path = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    imported_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )

    job = relationship("ImportJob", back_populates="imported_files")
    run = relationship("ImportRun", back_populates="imported_files")
