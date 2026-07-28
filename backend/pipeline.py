"""Background reel generation — mirrors Streamlit app.py button handler."""

from __future__ import annotations

import os
import shutil
import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend import jobs
from services.scene_utils import scene_narration
from services.video_builder import VideoBuilder
from workflows.graph import memory, reel_app


@dataclass
class PipelineRequest:
  prompt: str
  duration: int
  style: str
  platform: str
  voice: str
  dev_mode: str
  api_key: str
  eleven_key: Optional[str] = None
  music_path: Optional[str] = None
  duck_volume: float = 0.1


def _settings_changed(prev: Dict[str, Any], req: PipelineRequest) -> bool:
  return (
    prev.get("dev_mode") != req.dev_mode
    or prev.get("raw_prompt") != req.prompt
    or prev.get("duration") != req.duration
    or prev.get("style") != req.style
    or prev.get("platform") != req.platform
    or prev.get("voice_gender") != req.voice
  )


def _clear_generated_assets(run_dir: str) -> None:
  for sub in ("images", "audio"):
    path = os.path.join(run_dir, sub)
    if os.path.isdir(path):
      shutil.rmtree(path, ignore_errors=True)
  for name in ("final_reel.mp4", "subtitles.srt"):
    path = os.path.join(run_dir, name)
    if os.path.exists(path):
      os.remove(path)


def run_pipeline(job_id: str, req: PipelineRequest) -> None:
  run_dir = os.path.join("assets", job_id)
  os.makedirs(run_dir, exist_ok=True)
  jobs.update_job(job_id, run_dir=run_dir)

  try:
    os.environ["GOOGLE_API_KEY"] = req.api_key

    config = {"configurable": {"thread_id": job_id}}
    initial_state = {
      "raw_prompt": req.prompt,
      "duration": req.duration,
      "style": req.style,
      "platform": req.platform,
      "voice_gender": req.voice,
      "dev_mode": req.dev_mode,
      "run_dir": run_dir,
    }

    jobs.set_progress(
      job_id,
      "Creative Agents are processing workflow (including images)...",
      5,
    )

    current_state = reel_app.get_state(config)

    # Resume only for interrupted runs with unchanged settings.
    # Completed jobs (or changed mode/prompt/etc.) must start over — otherwise
    # users keep getting the same reel after flipping Generation Mode.
    restart = False
    if current_state.values:
      if not current_state.next:
        restart = True
        reason = "previous run completed"
      elif _settings_changed(current_state.values, req):
        restart = True
        reason = "settings changed"
      if restart:
        print(f"[pipeline] restarting job {job_id} ({reason}, dev_mode={req.dev_mode})")
        memory.delete_thread(job_id)
        _clear_generated_assets(run_dir)
        current_state = reel_app.get_state(config)

    if not current_state.values:
      print(f"[pipeline] starting fresh job {job_id} (dev_mode={req.dev_mode})")
      final_state = reel_app.invoke(initial_state, config=config)
    elif current_state.next:
      reel_app.update_state(
        config,
        {
          "dev_mode": req.dev_mode,
          "run_dir": run_dir,
          "voice_gender": req.voice,
        },
      )
      print(
        f"[pipeline] resuming job {job_id} from {list(current_state.next)} "
        f"(dev_mode={req.dev_mode})"
      )
      final_state = reel_app.invoke(None, config=config)
    else:
      final_state = current_state.values

    jobs.set_progress(job_id, "Creative agents finished. Preparing audio...", 50)

    scenes = final_state["image_prompts"]
    jobs.update_job(job_id, agent_outputs=scenes)

    vid_builder = VideoBuilder(
      run_dir=run_dir,
      elevenlabs_api_key=req.eleven_key or None,
      bg_music_path=req.music_path,
      duck_volume=req.duck_volume,
    )

    for idx, scene in enumerate(scenes):
      jobs.set_progress(
        job_id,
        f"Voice Director AI generating audio for scene {scene['scene']}...",
        50 + int(40 * ((idx + 1) / len(scenes))),
      )
      audio_path = os.path.join(run_dir, "audio", f"scene_{scene['scene']}.mp3")
      if not os.path.exists(audio_path):
        narration = scene_narration(scene)
        if not narration:
          raise ValueError(
            f"Scene {scene['scene']} has empty narration — cannot generate voice/subtitles. "
            "Re-run with a fresh job after the planner schema update."
          )
        vid_builder.generate_voice(narration, f"scene_{scene['scene']}", req.voice)

    jobs.set_progress(job_id, "Video Editor AI assembling the final reel...", 90)
    output_mp4 = vid_builder.assemble(scenes)
    subtitles_path = os.path.join(run_dir, "subtitles.srt")

    jobs.set_done(
      job_id,
      run_dir=run_dir,
      video_path=output_mp4,
      subtitles_path=subtitles_path,
      agent_outputs=scenes,
    )
  except Exception as e:
    traceback.print_exc()
    jobs.set_failed(job_id, str(e))
