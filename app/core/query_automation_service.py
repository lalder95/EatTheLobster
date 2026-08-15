from __future__ import annotations

import logging
import pathlib
import re
import shutil
import threading
from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.data.database import get_session, get_target_engine
from app.data.repositories import (
    DbConnectionRepository,
    QueryAutomationSettingsRepository,
    QueryRunRepository,
)

logger = logging.getLogger(__name__)
_GO_BATCH_RE = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


class QueryAutomationService:
    _instance: Optional["QueryAutomationService"] = None

    @classmethod
    def get_instance(cls) -> "QueryAutomationService":
        if cls._instance is None:
            cls._instance = QueryAutomationService()
        return cls._instance

    def __init__(self) -> None:
        self._interval_seconds = 30
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._scan_lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="QueryAutomationService",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info("Query automation service started")

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._running = False
        logger.info("Query automation service stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def scan_now(self) -> int:
        return self.scan_once(trigger_type="manual")

    def scan_once(self, trigger_type: str = "scheduled") -> int:
        if not self._scan_lock.acquire(blocking=False):
            logger.info("Query scan already in progress; skipping %s scan", trigger_type)
            return 0

        try:
            return self._scan_once_locked(trigger_type=trigger_type)
        finally:
            self._scan_lock.release()

    def _run_loop(self) -> None:
        self.scan_once(trigger_type="scheduled")
        while not self._stop_event.wait(self._interval_seconds):
            self.scan_once(trigger_type="scheduled")

    def _scan_once_locked(self, trigger_type: str) -> int:
        session = get_session()
        try:
            settings_repo = QueryAutomationSettingsRepository(session)
            settings = settings_repo.get()

            if not settings.enabled:
                logger.debug("Query automation is disabled")
                return 0

            if not settings.query_folder_path:
                logger.warning("Query automation folder is not configured")
                return 0

            if not settings.default_db_connection_id:
                logger.warning("Query automation database connection is not configured")
                return 0

            folder = pathlib.Path(settings.query_folder_path).expanduser()
            if not folder.exists() or not folder.is_dir():
                logger.warning("Query automation folder does not exist: %s", folder)
                return 0

            archive_dir = folder / (settings.archive_folder_name or "archive")
            archive_dir.mkdir(parents=True, exist_ok=True)

            query_files = sorted(
                path for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() == ".sql"
            )
            if not query_files:
                logger.debug("No query files found in %s", folder)
                return 0

            processed = 0
            for file_path in query_files:
                if self._process_query_file(
                    file_path=file_path,
                    archive_dir=archive_dir,
                    settings=settings,
                    trigger_type=trigger_type,
                ):
                    processed += 1

            return processed
        finally:
            session.close()

    def _process_query_file(
        self,
        file_path: pathlib.Path,
        archive_dir: pathlib.Path,
        settings,
        trigger_type: str,
    ) -> bool:
        session = get_session()
        run_repo = QueryRunRepository(session)
        db_repo = DbConnectionRepository(session)

        run = run_repo.create(
            query_name=file_path.stem,
            query_file_path=str(file_path),
            trigger_type=trigger_type,
            db_connection_id=settings.default_db_connection_id,
        )

        try:
            conn = db_repo.get_by_id(settings.default_db_connection_id)
            if conn is None:
                raise ValueError("Configured database connection was not found")

            query_text = self._normalize_query_text(
                file_path.read_text(encoding="utf-8-sig")
            )
            if not query_text:
                raise ValueError("Query file is empty")

            engine = get_target_engine(conn)
            try:
                with engine.connect() as connection:
                    rows = []
                    columns: list[str] = []
                    found_result_set = False
                    for batch in self._split_query_batches(query_text):
                        result = connection.execute(text(batch))
                        if result.returns_rows:
                            rows = result.fetchall()
                            columns = list(result.keys())
                            found_result_set = True
                    if not found_result_set:
                        raise ValueError("Query did not return a result set")
            finally:
                engine.dispose()

            frame = pd.DataFrame(rows, columns=columns)
            output_path = file_path.with_suffix(".xlsx")
            output_format = "xlsx"
            try:
                frame.to_excel(output_path, index=False)
            except Exception as excel_exc:
                logger.warning(
                    "Excel export failed for %s; falling back to CSV: %s",
                    file_path,
                    excel_exc,
                )
                output_path = file_path.with_suffix(".csv")
                output_format = "csv"
                frame.to_csv(output_path, index=False)

            archived_path = self._archive_source_file(file_path, archive_dir)

            run_repo.complete_by_id(
                run.id,
                status="success",
                row_count=len(frame),
                output_file_path=str(output_path),
                archived_file_path=str(archived_path),
            )
            logger.info(
                "Processed query file %s -> %s (%s, %s row(s))",
                file_path,
                output_path,
                output_format,
                len(frame),
            )
            return True
        except Exception as exc:
            logger.exception("Query file %s failed: %s", file_path, exc)
            run_repo.complete_by_id(
                run.id,
                status="failed",
                row_count=0,
                error_message=str(exc),
            )
            return False
        finally:
            session.close()

    def _normalize_query_text(self, raw_text: str) -> str:
        text_value = raw_text.strip()
        fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text_value, re.IGNORECASE | re.DOTALL)
        if fence_match:
            text_value = fence_match.group(1).strip()
        text_value = text_value.strip("`\n\r\t ")
        return text_value

    def _split_query_batches(self, query_text: str) -> list[str]:
        batches = [batch.strip() for batch in _GO_BATCH_RE.split(query_text)]
        return [batch for batch in batches if batch]

    def _archive_source_file(
        self,
        file_path: pathlib.Path,
        archive_dir: pathlib.Path,
    ) -> pathlib.Path:
        destination = archive_dir / file_path.name
        if destination.exists():
            destination = self._make_unique_path(destination)
        shutil.move(str(file_path), str(destination))
        return destination

    def _make_unique_path(self, path: pathlib.Path) -> pathlib.Path:
        counter = 1
        candidate = path
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        return candidate