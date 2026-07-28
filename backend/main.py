"""FastAPI entrypoint for Script2Reel web UI + API."""

from __future__ import annotations

import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs
from backend.models import AgentOutputsResponse, JobCreateResponse, JobStatusResponse
from backend.pipeline import PipelineRequest, run_pipeline

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
ASSETS_DIR = ROOT_DIR / "assets"

# Run long pipeline work off the event loop so status polling stays responsive.
_executor = ThreadPoolExecutor(max_workers=2)

app = FastAPI(title="Script2Reel", version="1.0.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


@app.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(
  prompt: str = Form(...),
  duration: int = Form(30),
  style: str = Form("Motivational"),
  platform: str = Form("Instagram Reels"),
  voice: str = Form("Male"),
  dev_mode: str = Form("mock"),
  api_key: str = Form(...),
  eleven_key: Optional[str] = Form(None),
  duck_volume: float = Form(0.1),
  job_id: Optional[str] = Form(None),
  bg_music: Optional[UploadFile] = File(None),
):
  if not api_key or not api_key.strip():
    raise HTTPException(status_code=400, detail="Gemini API Key is required.")

  if duration not in (15, 30, 60):
    raise HTTPException(status_code=400, detail="Duration must be 15, 30, or 60.")

  if style not in ("Motivational", "Educational", "Cinematic", "Documentary"):
    raise HTTPException(status_code=400, detail="Invalid style.")

  if platform not in ("Instagram Reels", "TikTok", "YouTube Shorts"):
    raise HTTPException(status_code=400, detail="Invalid platform.")

  if voice not in ("Male", "Female"):
    raise HTTPException(status_code=400, detail="Invalid voice.")

  if dev_mode not in ("mock", "fast", "production"):
    raise HTTPException(status_code=400, detail="Invalid generation mode.")

  # Resume: reuse provided job_id when present; otherwise mint a new one.
  if job_id and job_id.strip():
    resolved_id = job_id.strip()
    existing = jobs.get_job(resolved_id)
    if existing and existing["status"] == "running":
      raise HTTPException(status_code=409, detail="Job is already running.")
    if not existing:
      jobs.create_job(resolved_id)
    else:
      jobs.update_job(
        resolved_id,
        status="queued",
        stage="Queued",
        progress=0,
        error=None,
      )
  else:
    resolved_id = str(uuid.uuid4())
    jobs.create_job(resolved_id)

  run_dir = ASSETS_DIR / resolved_id
  run_dir.mkdir(parents=True, exist_ok=True)

  music_path = None
  if bg_music and bg_music.filename:
    safe_name = Path(bg_music.filename).name
    music_path = str(run_dir / f"bg_{safe_name}")
    content = await bg_music.read()
    with open(music_path, "wb") as f:
      f.write(content)

  req = PipelineRequest(
    prompt=prompt,
    duration=duration,
    style=style,
    platform=platform,
    voice=voice,
    dev_mode=dev_mode,
    api_key=api_key.strip(),
    eleven_key=(eleven_key.strip() if eleven_key else None) or None,
    music_path=music_path,
    duck_volume=duck_volume,
  )

  _executor.submit(run_pipeline, resolved_id, req)
  return JobCreateResponse(job_id=resolved_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
  job = jobs.get_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found.")
  return JobStatusResponse(
    job_id=job["job_id"],
    status=job["status"],
    stage=job.get("stage") or "",
    progress=job.get("progress") or 0,
    error=job.get("error"),
  )


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
  job = jobs.get_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found.")

  video_path = job.get("video_path") or str(ASSETS_DIR / job_id / "final_reel.mp4")
  if not os.path.exists(video_path):
    raise HTTPException(status_code=404, detail="Video not ready.")

  return FileResponse(
    video_path,
    media_type="video/mp4",
    filename="final_reel.mp4",
  )


@app.get("/api/jobs/{job_id}/subtitles")
async def get_job_subtitles(job_id: str):
  job = jobs.get_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found.")

  subtitles_path = job.get("subtitles_path") or str(ASSETS_DIR / job_id / "subtitles.srt")
  if not os.path.exists(subtitles_path):
    raise HTTPException(status_code=404, detail="Subtitles not ready.")

  return FileResponse(
    subtitles_path,
    media_type="text/plain",
    filename="subtitles.srt",
  )


@app.get("/api/jobs/{job_id}/agent-outputs", response_model=AgentOutputsResponse)
async def get_agent_outputs(job_id: str):
  job = jobs.get_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found.")

  scenes = job.get("agent_outputs")
  if scenes is None:
    raise HTTPException(status_code=404, detail="Agent outputs not ready.")

  return AgentOutputsResponse(job_id=job_id, scenes=scenes)


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
  job = jobs.get_job(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found.")

  run_dir = job.get("run_dir") or str(ASSETS_DIR / job_id)
  if os.path.isdir(run_dir):
    shutil.rmtree(run_dir, ignore_errors=True)

  jobs.delete_job(job_id)
  return {"ok": True, "job_id": job_id}


@app.get("/")
async def serve_index():
  index = FRONTEND_DIR / "index.html"
  if not index.exists():
    raise HTTPException(status_code=404, detail="Frontend not found.")
  return FileResponse(index)


if FRONTEND_DIR.is_dir():
  app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
