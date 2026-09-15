"""In-process background job registry.

Deliberately simple (no Redis/Celery): document processing runs in a worker
thread pool and progress is exposed for polling via
``GET /api/documents/{id}/status``. The Document row remains the durable
source of truth; the registry adds fine-grained live progress. If processing
throughput ever becomes a bottleneck, this interface is the swap point for a
real task queue.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from app.core.logging_conf import get_logger

logger = get_logger("jobs")


@dataclass
class JobInfo:
    job_id: str
    kind: str
    status: str = "queued"          # queued | running | completed | failed
    stage: str = "queued"
    progress: int = 0               # 0..100
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": (
                round((self.finished_at - self.started_at) * 1000, 1)
                if self.started_at and self.finished_at else None
            ),
            "result": self.result,
        }


class JobRegistry:
    def __init__(self, max_workers: int = 2):
        self._jobs: Dict[str, JobInfo] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="kiq-job")

    def submit(self, job_id: str, kind: str, fn: Callable[[Callable[[str, int], None]], None]) -> JobInfo:
        """Submit ``fn(progress_cb)``; progress_cb(stage, percent)."""
        info = JobInfo(job_id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = info

        def _run() -> None:
            with self._lock:
                info.status = "running"
                info.started_at = time.time()

            def progress(stage: str, percent: int) -> None:
                with self._lock:
                    info.stage = stage
                    info.progress = max(0, min(100, percent))

            try:
                fn(progress)
                with self._lock:
                    info.status = "completed"
                    info.stage = "completed"
                    info.progress = 100
                    info.finished_at = time.time()
                logger.info("Job %s (%s) completed in %.1fms", job_id, kind,
                            (info.finished_at - info.started_at) * 1000)
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    info.status = "failed"
                    info.stage = "failed"
                    info.error = str(exc)[:400]
                    info.finished_at = time.time()
                logger.exception("Job %s (%s) failed: %s", job_id, kind, exc)

        self._executor.submit(_run)
        return info

    def get(self, job_id: str) -> Optional[JobInfo]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_result(self, job_id: str, **result) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.result.update(result)

    def shutdown(self) -> None:  # pragma: no cover
        self._executor.shutdown(wait=False, cancel_futures=True)


_registry: Optional[JobRegistry] = None
_registry_lock = threading.Lock()


def get_job_registry() -> JobRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = JobRegistry()
        return _registry
