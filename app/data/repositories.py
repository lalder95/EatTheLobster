import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.data.models import (
    ColumnMapping,
    DbConnection,
    ImportedFile,
    ImportError,
    ImportJob,
    ImportRun,
)


class DbConnectionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self) -> List[DbConnection]:
        return self.session.query(DbConnection).all()

    def get_by_id(self, conn_id: int) -> Optional[DbConnection]:
        return (
            self.session.query(DbConnection).filter_by(id=conn_id).first()
        )

    def create(
        self,
        name: str,
        host: str,
        port: int,
        database_name: str,
        username: str,
        encrypted_password: str,
        db_type: str = "mysql",
        use_windows_auth: bool = False,
        instance_name: Optional[str] = None,
    ) -> DbConnection:
        conn = DbConnection(
            name=name,
            host=host,
            port=port,
            database_name=database_name,
            username=username,
            encrypted_password=encrypted_password,
            db_type=db_type,
            use_windows_auth=use_windows_auth,
            instance_name=instance_name,
        )
        self.session.add(conn)
        self.session.commit()
        self.session.refresh(conn)
        return conn

    def update(self, conn: DbConnection) -> DbConnection:
        conn.updated_at = datetime.datetime.utcnow()
        self.session.commit()
        self.session.refresh(conn)
        return conn

    def delete(self, conn_id: int) -> None:
        conn = self.get_by_id(conn_id)
        if conn:
            self.session.delete(conn)
            self.session.commit()


class ImportJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self) -> List[ImportJob]:
        return (
            self.session.query(ImportJob)
            .options(joinedload(ImportJob.db_connection))
            .order_by(ImportJob.name)
            .all()
        )

    def get_enabled(self) -> List[ImportJob]:
        return (
            self.session.query(ImportJob)
            .filter_by(enabled=True)
            .options(joinedload(ImportJob.db_connection))
            .all()
        )

    def get_by_id(self, job_id: int) -> Optional[ImportJob]:
        return (
            self.session.query(ImportJob)
            .filter_by(id=job_id)
            .options(
                joinedload(ImportJob.db_connection),
                joinedload(ImportJob.column_mappings),
            )
            .first()
        )

    def create(self, **kwargs) -> ImportJob:
        job = ImportJob(**kwargs)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def update(self, job: ImportJob) -> ImportJob:
        job.updated_at = datetime.datetime.utcnow()
        self.session.commit()
        self.session.refresh(job)
        return job

    def delete(self, job_id: int) -> None:
        job = self.get_by_id(job_id)
        if job:
            self.session.delete(job)
            self.session.commit()


class ColumnMappingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_job(self, job_id: int) -> List[ColumnMapping]:
        return (
            self.session.query(ColumnMapping).filter_by(job_id=job_id).all()
        )

    def replace_for_job(
        self, job_id: int, mappings: List[dict]
    ) -> List[ColumnMapping]:
        self.session.query(ColumnMapping).filter_by(job_id=job_id).delete()
        new_mappings = [
            ColumnMapping(
                job_id=job_id,
                source_column=m["source"],
                target_column=m["target"],
            )
            for m in mappings
        ]
        self.session.add_all(new_mappings)
        self.session.commit()
        return new_mappings


class ImportRunRepository:
    def finalize_running_runs(self, status: str = "failed", job_id: Optional[int] = None) -> int:
        """
        Finds all ImportRun records with status 'running' (optionally filtered by job_id),
        marks them as the given status, sets completed_at, and returns the count of affected runs.
        """
        query = self.session.query(ImportRun).filter_by(status="running")
        if job_id is not None:
            query = query.filter_by(job_id=job_id)
        runs = query.all()
        for run in runs:
            run.status = status
            run.completed_at = datetime.datetime.utcnow()
        self.session.commit()
        return len(runs)

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, job_id: int, trigger_type: str = "scheduled"
    ) -> ImportRun:
        run = ImportRun(
            job_id=job_id,
            trigger_type=trigger_type,
            started_at=datetime.datetime.utcnow(),
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def update_progress_by_id(
        self,
        run_id: int,
        files_processed: int,
        rows_imported: int,
        rows_skipped: int,
    ) -> bool:
        run = self.session.query(ImportRun).filter_by(id=run_id).first()
        if run is None:
            return False
        run.files_processed = files_processed
        run.rows_imported = rows_imported
        run.rows_skipped = rows_skipped
        self.session.commit()
        return True

    def complete_by_id(
        self,
        run_id: int,
        status: str,
        files_processed: int = 0,
        rows_imported: int = 0,
        rows_skipped: int = 0,
    ) -> bool:
        run = self.session.query(ImportRun).filter_by(id=run_id).first()
        if run is None:
            return False
        run.status = status
        run.completed_at = datetime.datetime.utcnow()
        run.files_processed = files_processed
        run.rows_imported = rows_imported
        run.rows_skipped = rows_skipped
        self.session.commit()
        return True

    def complete(
        self,
        run: ImportRun,
        status: str,
        files_processed: int = 0,
        rows_imported: int = 0,
        rows_skipped: int = 0,
    ) -> ImportRun:
        run.status = status
        run.completed_at = datetime.datetime.utcnow()
        run.files_processed = files_processed
        run.rows_imported = rows_imported
        run.rows_skipped = rows_skipped
        self.session.commit()
        return run

    def get_recent(
        self, limit: int = 200, job_id: Optional[int] = None
    ) -> List[ImportRun]:
        query = self.session.query(ImportRun).options(
            joinedload(ImportRun.job)
        )
        if job_id is not None:
            query = query.filter_by(job_id=job_id)
        return query.order_by(ImportRun.started_at.desc()).limit(limit).all()

    def get_last_run(self, job_id: int) -> Optional[ImportRun]:
        return (
            self.session.query(ImportRun)
            .filter_by(job_id=job_id)
            .order_by(ImportRun.started_at.desc())
            .first()
        )


class ImportErrorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        run_id: int,
        error_type: str,
        error_message: str,
        file_path: Optional[str] = None,
    ) -> ImportError:
        error = ImportError(
            run_id=run_id,
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            occurred_at=datetime.datetime.utcnow(),
        )
        self.session.add(error)
        self.session.commit()
        return error

    def get_by_run(self, run_id: int) -> List[ImportError]:
        return (
            self.session.query(ImportError).filter_by(run_id=run_id).all()
        )


class ImportedFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def is_imported(self, job_id: int, content_hash: str) -> bool:
        return (
            self.session.query(ImportedFile)
            .filter_by(job_id=job_id, content_hash=content_hash)
            .first()
        ) is not None

    def record(
        self,
        job_id: int,
        file_path: str,
        content_hash: str,
        run_id: Optional[int] = None,
    ) -> ImportedFile:
        imported = ImportedFile(
            job_id=job_id,
            file_path=file_path,
            content_hash=content_hash,
            run_id=run_id,
            imported_at=datetime.datetime.utcnow(),
        )
        self.session.add(imported)
        self.session.commit()
        return imported

    def clear_for_job(self, job_id: int) -> None:
        self.session.query(ImportedFile).filter_by(job_id=job_id).delete()
        self.session.commit()
