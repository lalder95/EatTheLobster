import datetime
import logging
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.time_utils import local_tzinfo

logger = logging.getLogger(__name__)


def _resolve_scheduler_timezone():
    # Prefer explicit local timezone resolution.
    try:
        from tzlocal import get_localzone

        return get_localzone()
    except Exception as exc:
        logger.warning(
            "Could not resolve local timezone via tzlocal; using machine local tz. %s",
            exc,
        )
        return local_tzinfo()


class SchedulerService:
    _instance: Optional["SchedulerService"] = None

    @classmethod
    def get_instance(cls) -> "SchedulerService":
        if cls._instance is None:
            cls._instance = SchedulerService()
        return cls._instance

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(
            timezone=_resolve_scheduler_timezone()
        )
        self._running = False
        self._lock = threading.Lock()
        self._running_jobs: set[int] = set()
        self._stop_requests: dict[int, threading.Event] = {}

    def start(self) -> None:
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started")
            self._reconcile_stale_running_runs()
            self._load_all_jobs()

    def stop(self) -> None:
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Scheduler stopped")

    def _load_all_jobs(self) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportJobRepository

        session = get_session()
        try:
            repo = ImportJobRepository(session)
            jobs = repo.get_enabled()
            for job in jobs:
                self._schedule_job(job)
            logger.info(f"Loaded {len(jobs)} enabled job(s) into scheduler")
        finally:
            session.close()

    def _make_trigger(self, job):
        config = job.frequency_config_dict
        freq_type = job.frequency_type

        if freq_type == "interval":
            minutes = int(config.get("minutes", 60))
            return IntervalTrigger(minutes=minutes)

        if freq_type == "daily":
            h, m = config["time"].split(":")
            return CronTrigger(hour=int(h), minute=int(m))

        if freq_type == "weekly":
            h, m = config["time"].split(":")
            return CronTrigger(
                day_of_week=int(config["weekday"]),
                hour=int(h),
                minute=int(m),
            )

        raise ValueError(f"Unknown frequency type: '{freq_type}'")

    def _schedule_job(self, job) -> None:
        try:
            trigger = self._make_trigger(job)
            self._scheduler.add_job(
                func=_execute_job,
                trigger=trigger,
                id=f"job_{job.id}",
                args=[job.id],
                replace_existing=True,
                misfire_grace_time=120,
                coalesce=True,
                max_instances=1,
            )
            logger.info(f"Scheduled job '{job.name}' (id={job.id})")
        except Exception as exc:
            logger.error(f"Failed to schedule job {job.id}: {exc}")

    def schedule_job(self, job) -> None:
        if not self._running:
            return
        if job.enabled:
            self._schedule_job(job)
        else:
            self.unschedule_job(job.id)

    def unschedule_job(self, job_id: int) -> None:
        if self._running:
            try:
                self._scheduler.remove_job(f"job_{job_id}")
                logger.info(f"Unscheduled job {job_id}")
            except Exception:
                pass

    def trigger_now(self, job_id: int, force_full_refresh: bool = False) -> None:
        self._run_job(
            job_id,
            trigger_type="manual",
            force_full_refresh=force_full_refresh,
        )

    def _begin_job(self, job_id: int) -> bool:
        with self._lock:
            if job_id in self._running_jobs:
                return False
            self._running_jobs.add(job_id)
            self._stop_requests[job_id] = threading.Event()
            return True

    def _finish_job(self, job_id: int) -> None:
        with self._lock:
            self._running_jobs.discard(job_id)
            self._stop_requests.pop(job_id, None)
        self._reconcile_stale_running_runs(job_id=job_id)

    def _reconcile_stale_running_runs(self, job_id: Optional[int] = None) -> None:
        from app.data.database import get_session
        from app.data.repositories import ImportRunRepository

        session = get_session()
        try:
            fixed = ImportRunRepository(session).finalize_running_runs(
                status="failed",
                job_id=job_id,
            )
            if fixed:
                if job_id is None:
                    logger.warning(
                        "Reconciled %s stale running run(s) left by previous execution.",
                        fixed,
                    )
                else:
                    logger.warning(
                        "Reconciled %s stale running run(s) for job %s.",
                        fixed,
                        job_id,
                    )
        finally:
            session.close()

    def _run_job(
        self,
        job_id: int,
        trigger_type: str,
        force_full_refresh: bool = False,
    ) -> None:
        from app.core.etl_engine import ETLEngine

        if not self._begin_job(job_id):
            logger.warning("Job %s is already running", job_id)
            return

        try:
            ETLEngine().run_job(
                job_id,
                trigger_type=trigger_type,
                force_full_refresh=force_full_refresh,
            )
        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
        finally:
            self._finish_job(job_id)

    def request_stop(self, job_id: int) -> bool:
        with self._lock:
            stop_event = self._stop_requests.get(job_id)
            if stop_event is None:
                return False
            stop_event.set()
            return True

    def is_stop_requested(self, job_id: int) -> bool:
        with self._lock:
            stop_event = self._stop_requests.get(job_id)
            return stop_event.is_set() if stop_event else False

    def is_job_running(self, job_id: int) -> bool:
        with self._lock:
            return job_id in self._running_jobs

    def get_running_job_count(self) -> int:
        with self._lock:
            return len(self._running_jobs)

    def get_next_run_time(self, job_id: int) -> Optional[datetime.datetime]:
        aps_job = self._scheduler.get_job(f"job_{job_id}")
        return aps_job.next_run_time if aps_job else None

    def reschedule_all(self) -> None:
        if self._running:
            self._scheduler.remove_all_jobs()
            self._load_all_jobs()

    @property
    def is_running(self) -> bool:
        return self._running


def _execute_job(job_id: int) -> None:
    service = SchedulerService.get_instance()

    try:
        service._run_job(job_id, trigger_type="scheduled")
    except Exception as exc:
        logger.exception(
            f"Unhandled error in scheduled job {job_id}: {exc}"
        )
