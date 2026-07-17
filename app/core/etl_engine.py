import logging
import pathlib
import re
import time
from typing import List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from app.core.date_stamp_service import DateStampService
from app.core.dedupe_service import DedupeService
from app.core.file_reader import FileReader, SUPPORTED_EXTENSIONS
from app.core.mapping_service import MappingService
from app.core.schema_export_service import SchemaExportService
from app.data.database import get_target_engine, get_session, quote_name
from app.data.models import ImportRun
from app.data.repositories import (
    ImportedFileRepository,
    ImportErrorRepository,
    ImportJobRepository,
    ImportRunRepository,
)

logger = logging.getLogger(__name__)

_VALID_TABLE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


class ETLEngine:
    def __init__(self) -> None:
        self.file_reader = FileReader()
        self.dedupe_service = DedupeService()
        self.date_stamp_service = DateStampService()
        self.mapping_service = MappingService()
        self.schema_export_service = SchemaExportService()

    def run_job(
        self,
        job_id: int,
        trigger_type: str = "scheduled",
        force_full_refresh: bool = False,
    ) -> Optional[ImportRun]:
        session = get_session()
        try:
            job_repo = ImportJobRepository(session)
            run_repo = ImportRunRepository(session)
            error_repo = ImportErrorRepository(session)
            imported_file_repo = ImportedFileRepository(session)

            job = job_repo.get_by_id(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return None

            job_type = getattr(job, "job_type", "import") or "import"
            if job_type == "schema_export":
                return self._run_schema_export_job(
                    job=job,
                    run_repo=run_repo,
                    error_repo=error_repo,
                    trigger_type=trigger_type,
                )

            logger.info(
                f"Starting run for job '{job.name}' "
                f"(id={job_id}, trigger={trigger_type})"
            )
            run = run_repo.create(job_id=job_id, trigger_type=trigger_type)
            run_id = run.id

            files = self._get_files(job)
            if not files:
                logger.warning(
                    f"No supported files found for job '{job.name}' "
                    f"at '{job.source_path}'"
                )
                self._complete_run_with_retry(
                    run_id=run_id,
                    status="success",
                    files_processed=0,
                    rows_imported=0,
                    rows_skipped=0,
                )
                return run

            target_engine = get_target_engine(job.db_connection)
            full_refresh = force_full_refresh or (not job.append_mode)

            if full_refresh:
                logger.info(
                    "Starting full refresh for job '%s' (clear import history + purge target table)",
                    job.name,
                )
                imported_file_repo.clear_for_job(job_id)
                self._truncate_target_table(job.target_table, target_engine)

            total_rows = 0
            total_skipped = 0
            processed = 0
            has_errors = False
            was_cancelled = False

            for file_path in files:
                try:
                    if self._is_stop_requested(job_id):
                        was_cancelled = True
                        logger.info(
                            "Stop requested for job '%s' before file '%s'",
                            job.name,
                            file_path,
                        )
                        break

                    content_hash = self.dedupe_service.compute_hash(file_path)
                    if job.ignore_previously_imported and imported_file_repo.is_imported(
                        job_id, content_hash
                    ):
                        logger.debug(
                            f"Skipping already-imported file: {file_path}"
                        )
                        total_skipped += 1
                        self._update_run_progress_with_retry(
                            run_id=run_id,
                            files_processed=processed,
                            rows_imported=total_rows,
                            rows_skipped=total_skipped,
                        )
                        continue

                    df = self.file_reader.read_file(file_path)
                    logger.debug(
                        f"Read {len(df)} rows from {file_path}"
                    )

                    if self._is_stop_requested(job_id):
                        was_cancelled = True
                        logger.info(
                            "Stop requested for job '%s' after reading '%s'",
                            job.name,
                            file_path,
                        )
                        break

                    if job.column_mappings:
                        validation_errors = self.mapping_service.validate_mapping(
                            df, job.column_mappings
                        )
                        if validation_errors:
                            raise ValueError(
                                "Mapping validation failed: "
                                + "; ".join(validation_errors)
                            )
                        df = self.mapping_service.apply_mapping(
                            df, job.column_mappings
                        )

                    if job.use_file_created_date and job.file_created_date_column:
                        file_time = self.date_stamp_service.get_file_created_time(
                            file_path
                        )
                        df = self.date_stamp_service.apply_timestamp(
                            df, job.file_created_date_column, file_time
                        )
                        self.date_stamp_service.ensure_timestamp_column(
                            target_engine,
                            job.target_table,
                            job.file_created_date_column,
                        )

                    if self._is_stop_requested(job_id):
                        was_cancelled = True
                        logger.info(
                            "Stop requested for job '%s' before writing '%s'",
                            job.name,
                            file_path,
                        )
                        break

                    rows = self._write_to_target(job, df, target_engine)
                    imported_file_repo.record(
                        job_id, str(file_path), content_hash, run.id
                    )
                    total_rows += rows
                    processed += 1
                    self._update_run_progress_with_retry(
                        run_id=run_id,
                        files_processed=processed,
                        rows_imported=total_rows,
                        rows_skipped=total_skipped,
                    )
                    logger.info(
                        f"Imported {rows} rows from '{file_path}'"
                    )

                except Exception as exc:
                    has_errors = True
                    logger.exception(
                        f"Error processing file '{file_path}': {exc}"
                    )
                    error_repo.create(
                        run_id=run.id,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        file_path=str(file_path),
                    )

            if was_cancelled:
                status = "cancelled"
            elif has_errors and processed == 0:
                status = "failed"
            elif has_errors:
                status = "partial"
            else:
                status = "success"
            final_status = status

            self._complete_run_with_retry(
                run_id=run_id,
                status=status,
                files_processed=processed,
                rows_imported=total_rows,
                rows_skipped=total_skipped,
            )
            logger.info(
                f"Job '{job.name}' complete: status={status}, "
                f"files={processed}, rows={total_rows}, skipped={total_skipped}"
            )
            return run
        finally:
            session.close()

    def _run_schema_export_job(
        self,
        job,
        run_repo: ImportRunRepository,
        error_repo: ImportErrorRepository,
        trigger_type: str,
    ) -> Optional[ImportRun]:
        run = run_repo.create(job_id=job.id, trigger_type=trigger_type)
        try:
            logger.info(
                "Starting schema export for job '%s' (id=%s, trigger=%s)",
                job.name,
                job.id,
                trigger_type,
            )

            output_path = getattr(job, "export_output_path", None)
            export_format = (getattr(job, "export_format", None) or "json").lower()

            if not output_path:
                raise ValueError(
                    "Schema export jobs require an export_output_path."
                )
            if export_format != "json":
                raise ValueError(
                    "Only JSON schema exports are currently supported."
                )

            output_file = self.schema_export_service.export_to_json(
                job.db_connection,
                output_path,
            )

            self._complete_run_with_retry(
                run_id=run.id,
                status="success",
                files_processed=1,
                rows_imported=0,
                rows_skipped=0,
            )
            logger.info(
                "Schema export complete for job '%s': output=%s",
                job.name,
                output_file,
            )
            return run
        except Exception as exc:
            logger.exception("Schema export job %s failed: %s", job.id, exc)
            error_repo.create(
                run_id=run.id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            self._complete_run_with_retry(
                run_id=run.id,
                status="failed",
                files_processed=0,
                rows_imported=0,
                rows_skipped=0,
            )
            raise
        finally:
            self._ensure_run_finalized(run.id, "failed")

    def _update_run_progress_with_retry(
        self,
        run_id: int,
        files_processed: int,
        rows_imported: int,
        rows_skipped: int,
    ) -> None:
        attempts = 3
        for attempt in range(1, attempts + 1):
            progress_session = get_session()
            try:
                ImportRunRepository(progress_session).update_progress_by_id(
                    run_id=run_id,
                    files_processed=files_processed,
                    rows_imported=rows_imported,
                    rows_skipped=rows_skipped,
                )
                return
            except OperationalError as exc:
                if "database is locked" in str(exc).lower() and attempt < attempts:
                    time.sleep(0.1 * attempt)
                    continue
                logger.warning(
                    "Could not update progress for run %s: %s",
                    run_id,
                    exc,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Could not update progress for run %s: %s",
                    run_id,
                    exc,
                )
                return
            finally:
                progress_session.close()

    def _complete_run_with_retry(
        self,
        run_id: int,
        status: str,
        files_processed: int = 0,
        rows_imported: int = 0,
        rows_skipped: int = 0,
    ) -> None:
        attempts = 5
        for attempt in range(1, attempts + 1):
            complete_session = get_session()
            try:
                ok = ImportRunRepository(complete_session).complete_by_id(
                    run_id=run_id,
                    status=status,
                    files_processed=files_processed,
                    rows_imported=rows_imported,
                    rows_skipped=rows_skipped,
                )
                if not ok:
                    logger.warning("Run %s not found during completion", run_id)
                return
            except OperationalError as exc:
                if "database is locked" in str(exc).lower() and attempt < attempts:
                    time.sleep(0.2 * attempt)
                    continue
                logger.exception(
                    "Failed to complete run %s with status '%s': %s",
                    run_id,
                    status,
                    exc,
                )
                return
            except Exception as exc:
                logger.exception(
                    "Failed to complete run %s with status '%s': %s",
                    run_id,
                    status,
                    exc,
                )
                return
            finally:
                complete_session.close()

    def _ensure_run_finalized(self, run_id: int, fallback_status: str) -> None:
        # Safety net: if a completion commit failed (e.g., transient SQLite lock),
        # don't leave the run stuck in "running" forever.
        attempts = 3
        for attempt in range(1, attempts + 1):
            fallback_session = get_session()
            try:
                run_repo = ImportRunRepository(fallback_session)
                fixed = run_repo.complete_by_id(
                    run_id=run_id,
                    status=fallback_status,
                )
                if fixed:
                    logger.warning(
                        "Recovered stuck run %s with fallback status '%s'.",
                        run_id,
                        fallback_status,
                    )
                return
            except OperationalError as exc:
                # SQLite can briefly lock under concurrent access; retry quickly.
                if "database is locked" in str(exc).lower() and attempt < attempts:
                    time.sleep(0.2 * attempt)
                    continue
                logger.exception(
                    "Failed to finalize run %s in safety net: %s",
                    run_id,
                    exc,
                )
                return
            except Exception as exc:
                logger.exception(
                    "Failed to finalize run %s in safety net: %s",
                    run_id,
                    exc,
                )
                return
            finally:
                fallback_session.close()

    def _is_stop_requested(self, job_id: int) -> bool:
        try:
            from app.scheduler.scheduler_service import SchedulerService

            return SchedulerService.get_instance().is_stop_requested(job_id)
        except Exception:
            return False

    def _get_files(self, job) -> List[pathlib.Path]:
        path = pathlib.Path(job.source_path)
        if job.source_type == "file":
            if path.exists() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                return [path]
            return []
        if job.source_type == "directory":
            if not path.is_dir():
                return []
            files: List[pathlib.Path] = []
            for ext in ("*.csv", "*.xlsx", "*.xls"):
                files.extend(path.glob(ext))
            return sorted(files)
        return []

    def _normalize_column_name(self, name: str) -> str:
        value = (name or "").strip().lower()
        value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")
        if not value:
            value = "column"
        if value[0].isdigit():
            value = f"col_{value}"
        return value[:64]

    def _align_dataframe_to_existing_table(
        self, df, target_table: str, inspector
    ):
        table_columns = [c["name"] for c in inspector.get_columns(target_table)]
        if not table_columns:
            return df

        table_set = set(table_columns)

        # Build a normalized lookup for columns created from file templates,
        # e.g. "Store Number" -> "store_number".
        normalized_lookup: dict[str, str] = {}
        for col in table_columns:
            normalized_lookup[self._normalize_column_name(col)] = col

        rename_map: dict[str, str] = {}
        for col in df.columns:
            if col in table_set:
                continue
            normalized = self._normalize_column_name(str(col))
            target_col = normalized_lookup.get(normalized)
            if target_col and target_col not in rename_map.values():
                rename_map[col] = target_col

        if rename_map:
            df = df.rename(columns=rename_map)
            logger.debug(f"Auto-aligned columns: {rename_map}")

        dropped = [c for c in df.columns if c not in table_set]
        if dropped:
            logger.warning(
                "Dropping source columns not present in target table "
                f"'{target_table}': {dropped[:10]}"
            )

        kept = [c for c in df.columns if c in table_set]
        if not kept:
            raise ValueError(
                f"No source columns match target table '{target_table}' columns."
            )

        return df[kept]

    def _resolve_existing_table_name(self, inspector, requested_name: str) -> Optional[str]:
        table_names = inspector.get_table_names()
        if requested_name in table_names:
            return requested_name

        requested_fold = requested_name.casefold()
        for table_name in table_names:
            if table_name.casefold() == requested_fold:
                return table_name
        return None

    def _truncate_target_table(self, target_table: str, engine) -> None:
        if not _VALID_TABLE.match(target_table):
            raise ValueError(
                f"Invalid target table name: '{target_table}'. "
                "Use only letters, digits, and underscores."
            )

        insp = inspect(engine)
        resolved_table = self._resolve_existing_table_name(insp, target_table)
        if resolved_table is None:
            logger.info(
                "Target table '%s' does not exist yet; skipping purge.",
                target_table,
            )
            return

        with engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {quote_name(engine, resolved_table)}"))
            conn.commit()
        logger.info("Purged target table '%s'", resolved_table)

    def _write_to_target(self, job, df, engine) -> int:
        target_table = job.target_table
        if not _VALID_TABLE.match(target_table):
            raise ValueError(
                f"Invalid target table name: '{target_table}'. "
                "Use only letters, digits, and underscores."
            )

        insp = inspect(engine)
        resolved_table = self._resolve_existing_table_name(insp, target_table)
        table_exists = resolved_table is not None
        table_for_write = resolved_table or target_table

        if table_exists:
            if table_for_write != target_table:
                logger.debug(
                    "Using database table name '%s' for requested '%s'",
                    table_for_write,
                    target_table,
                )
            df = self._align_dataframe_to_existing_table(df, table_for_write, insp)

        df.to_sql(table_for_write, engine, if_exists="append", index=False)
        return len(df)
