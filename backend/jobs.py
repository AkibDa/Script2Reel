"""In-memory job store and progress helpers."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional


_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def create_job(job_id: str) -> Dict[str, Any]:
  job = {
    "job_id": job_id,
    "status": "queued",
    "stage": "Queued",
    "progress": 0,
    "error": None,
    "run_dir": None,
    "video_path": None,
    "subtitles_path": None,
    "agent_outputs": None,
  }
  with _lock:
    _jobs[job_id] = job
  return job.copy()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
  with _lock:
    job = _jobs.get(job_id)
    return job.copy() if job else None


def update_job(job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
  with _lock:
    job = _jobs.get(job_id)
    if not job:
      return None
    job.update(fields)
    return job.copy()


def set_progress(job_id: str, stage: str, progress: int) -> None:
  update_job(
    job_id,
    status="running",
    stage=stage,
    progress=max(0, min(100, int(progress))),
  )


def set_done(
  job_id: str,
  *,
  run_dir: str,
  video_path: str,
  subtitles_path: str,
  agent_outputs: List[Dict[str, Any]],
) -> None:
  update_job(
    job_id,
    status="done",
    stage="Reel Generation Complete!",
    progress=100,
    error=None,
    run_dir=run_dir,
    video_path=video_path,
    subtitles_path=subtitles_path,
    agent_outputs=agent_outputs,
  )


def set_failed(job_id: str, error: str) -> None:
  update_job(
    job_id,
    status="failed",
    stage="Generation failed",
    error=error,
  )


def delete_job(job_id: str) -> bool:
  with _lock:
    if job_id not in _jobs:
      return False
    del _jobs[job_id]
    return True
