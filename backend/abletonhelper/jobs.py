"""Background work.

Analysis takes minutes, so nothing runs inside a request. Today that's a
thread pool in the API process -- fine for one person on a laptop. When
this becomes multi-tenant, swap `submit` for an RQ/Celery enqueue; the
Job row and the polling endpoint stay exactly as they are.
"""

from __future__ import annotations

import json
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .config import settings
from .db import Job, session

_pool = ThreadPoolExecutor(max_workers=settings.max_workers,
                           thread_name_prefix="ah-job")


def _update(job_id: str, **fields) -> None:
    with session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        s.commit()


class Progress:
    """Handed to job functions so they can report without touching the DB."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def __call__(self, fraction: float, message: str = "") -> None:
        _update(self.job_id, progress=max(0.0, min(1.0, fraction)),
                message=message or "")


def submit(kind: str, fn: Callable[[Progress], dict], target_id: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    with session() as s:
        s.add(Job(id=job_id, kind=kind, state="queued", target_id=target_id))
        s.commit()

    def run() -> None:
        _update(job_id, state="running", progress=0.0)
        try:
            result = fn(Progress(job_id))
            _update(job_id, state="done", progress=1.0,
                    result_json=json.dumps(result), message="")
        except Exception as e:
            _update(job_id, state="error", message=f"{type(e).__name__}: {e}",
                    result_json=json.dumps({"traceback": traceback.format_exc()}))

    _pool.submit(run)
    return job_id


def get(job_id: str) -> dict | None:
    with session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "kind": job.kind,
            "state": job.state,
            "progress": job.progress,
            "message": job.message,
            "target_id": job.target_id,
            "result": json.loads(job.result_json) if job.result_json else None,
        }
