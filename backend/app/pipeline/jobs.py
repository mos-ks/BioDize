"""In-process registry for background pipeline jobs.

A live PDF run (VLM + OCR over dozens of pages) takes minutes — far longer than
a Cloudflare quick tunnel's ~100s request limit. So ``POST /documents/process_async``
kicks off a background thread and returns a job id immediately; the UI polls
``GET /documents/jobs/{id}`` for progress and the final document id.

The registry is in-memory and single-process (hackathon-grade): jobs are lost on
a server restart, which is harmless because the finished Document is already
committed to the DB by the time the job reports ``processed``.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass

_LOCK = threading.Lock()
_JOBS: dict[str, "Job"] = {}
_MAX_JOBS = 50  # keep the registry from growing unbounded


@dataclass
class Job:
    id: str
    status: str = "processing"  # processing | processed | failed
    stage: str = "Starting…"    # human-readable current step
    page_done: int = 0
    page_total: int = 0
    document_id: str | None = None
    error: str | None = None
    started_at: float = 0.0
    final_ms: int = 0           # elapsed time, frozen once finished/failed

    def snapshot(self) -> dict:
        d = asdict(self)
        started = d.pop("started_at", 0.0) or 0.0
        final = d.pop("final_ms", 0)
        # Report live elapsed time while running; frozen once finished/failed.
        d["elapsed_ms"] = final if self.status != "processing" else (
            int((time.monotonic() - started) * 1000) if started else 0)
        d["job_id"] = d.pop("id")
        return d


def create() -> Job:
    job = Job(id=uuid.uuid4().hex, started_at=time.monotonic())
    with _LOCK:
        _JOBS[job.id] = job
        if len(_JOBS) > _MAX_JOBS:  # evict oldest
            for stale in list(_JOBS)[: len(_JOBS) - _MAX_JOBS]:
                _JOBS.pop(stale, None)
    return job


def get(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return job.snapshot() if job else None


def update(job_id: str, **fields) -> None:
    """Set any of stage / page_done / page_total (None values ignored)."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        for key, value in fields.items():
            if value is not None and hasattr(job, key):
                setattr(job, key, value)


def finish(job_id: str, document_id: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.status = "processed"
        job.document_id = document_id
        job.stage = "Done"
        job.final_ms = int((time.monotonic() - job.started_at) * 1000)


def fail(job_id: str, error: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error
        job.stage = "Failed"
        job.final_ms = int((time.monotonic() - job.started_at) * 1000)
