#services/video_builder.py

import os
import pysrt
import random
from PIL import Image, ImageFilter
import numpy as np
from moviepy import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip
from moviepy.video.fx import Resize, CrossFadeIn
from moviepy.audio.fx import MultiplyVolume
from services.scene_utils import scene_narration
from services.voice_provider import get_voice_provider


class VideoBuilder:
  def __init__(self, run_dir: str, elevenlabs_api_key: str = None, bg_music_path: str = None, duck_volume: float = 0.1, voice_provider=None):
    self.run_dir = run_dir
    self.voice_provider = voice_provider or get_voice_provider(elevenlabs_api_key=elevenlabs_api_key)
    self.bg_music_path = bg_music_path
    self.duck_volume = duck_volume

  def generate_voice(self, text: str, filename: str, voice_gender: str) -> str:
    text = (text or "").strip()
    if not text or text.lower() in ("none", "null"):
      raise ValueError(f"Cannot generate voice for '{filename}': narration is empty.")

    return self.voice_provider.generate(text, self.run_dir, filename, voice_gender=voice_gender)

  def generate_subtitles(self, scene_data: list, output_filename: str = "subtitles.srt"):
    filepath = os.path.join(self.run_dir, output_filename)
    subs = pysrt.SubRipFile()
    current_time_sec = 0.0

    for scene in scene_data:
      text = scene_narration(scene)
      if not text:
        print(f"[video_builder] WARNING empty narration for scene {scene.get('scene')}; skipping subtitle cue")
        current_time_sec += scene['duration']
        continue

      words = text.split()
      chunk_size = 4
      chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

      chunk_duration = scene['duration'] / len(chunks) if chunks else scene['duration']

      for chunk in chunks:
        start_time = current_time_sec
        end_time = current_time_sec + chunk_duration

        sub = pysrt.SubRipItem(
          index=len(subs) + 1,
          start=pysrt.SubRipTime(seconds=start_time),
          end=pysrt.SubRipTime(seconds=end_time),
          text=chunk
        )
        subs.append(sub)
        current_time_sec = end_time

    subs.save(filepath, encoding='utf-8')
    return filepath

  def _create_blurred_background(self, image_path: str, duration: int) -> ImageClip:
    """Updates blurred background for 16:9 dimensions."""

    img = Image.open(image_path).convert('RGB')
    # Resize width to 1920, maintain aspect ratio
    img = img.resize((1920, int(1920 * img.height / img.width)), Image.LANCZOS)
    # Crop to 1080 height
    img = img.crop((0, (img.height - 1080) // 2, 1920, (img.height + 1080) // 2))
    img = img.filter(ImageFilter.GaussianBlur(radius=30))

    bg_clip = ImageClip(np.array(img)).with_duration(duration)
    return bg_clip

  def apply_dynamic_motion(self, image_path: str, duration: int, zoom_factor: float = 1.15) -> ImageClip:
    motion_type = random.choice(["zoom_in", "pan_right", "pan_left", "pan_up", "pan_down"])
    base_clip = ImageClip(image_path).with_duration(duration)

    # Check against 16:9 ratio
    if base_clip.w / base_clip.h < 1920 / 1080:
      bg_clip = self._create_blurred_background(image_path, duration)
      fg_clip = base_clip.with_effects([Resize(height=1080)])
      fg_clip = fg_clip.with_position("center")
      clip = CompositeVideoClip([bg_clip, fg_clip])
    else:
      clip = base_clip.with_effects([Resize(width=1920)])
      if clip.h < 1080:
        clip = clip.with_effects([Resize(height=1080)])

    w, h = clip.w, clip.h
    target_w, target_h = 1920, 1080

    def effect_func(get_frame, t):
      p = t / duration

      if motion_type == "zoom_in":
        scale = 1 + (zoom_factor - 1) * p
        frame = clip.with_effects([Resize(scale)]).get_frame(t)
        cy, cx = frame.shape[0] // 2, frame.shape[1] // 2
        return frame[cy - target_h // 2:cy + target_h // 2, cx - target_w // 2:cx + target_w // 2]

      elif motion_type == "pan_right":
        max_pan = w - target_w
        cx = int(max_pan * p)
        return get_frame(t)[(h - target_h) // 2: (h + target_h) // 2, cx: cx + target_w]

      elif motion_type == "pan_left":
        max_pan = w - target_w
        cx = int(max_pan * (1 - p))
        return get_frame(t)[(h - target_h) // 2: (h + target_h) // 2, cx: cx + target_w]

      cy, cx = h // 2, w // 2
      return get_frame(t)[cy - target_h // 2:cy + target_h // 2, cx - target_w // 2:cx + target_w // 2]

    return clip.transform(effect_func)

  def assemble(self, scene_data: list, output_filename: str = "final_reel.mp4"):
    import time
    assemble_start = time.time()

    video_clips = []
    transition_duration = 0.3

    self.generate_subtitles(scene_data)

    for i, scene in enumerate(scene_data):
      vid_path = os.path.join(self.run_dir, "videos", f"scene_{scene['scene']}.mp4")
      audio_path = os.path.join(self.run_dir, "audio", f"scene_{scene['scene']}.mp3")

      if not os.path.exists(vid_path):
        raise FileNotFoundError(f"Missing required animation for assembly: {vid_path}")

      v_clip = VideoFileClip(vid_path).with_effects([Resize(height=1080)])

      if os.path.exists(audio_path):
        a_clip = AudioFileClip(audio_path)
        scene['duration'] = a_clip.duration + transition_duration
        from moviepy.video.fx import loop
        v_clip = loop(v_clip, duration=scene['duration']).with_audio(a_clip)

      if i > 0:
        v_clip = v_clip.with_effects([CrossFadeIn(transition_duration)])

      video_clips.append(v_clip)

    final_video = concatenate_videoclips(video_clips, padding=-transition_duration, method="compose")

    if self.bg_music_path and os.path.exists(self.bg_music_path):
      bg_music = AudioFileClip(self.bg_music_path)
      bg_music = bg_music.with_effects([MultiplyVolume(self.duck_volume)]).with_duration(final_video.duration)

      if final_video.audio:
        mixed_audio = CompositeAudioClip([final_video.audio, bg_music])
        final_video = final_video.with_audio(mixed_audio)
      else:
        final_video = final_video.with_audio(bg_music)

    output_path = os.path.join(self.run_dir, output_filename)
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    self._append_telemetry(assemble_start)
    return output_path

  def _append_telemetry(self, assemble_start: float) -> None:
    """Best-effort: merges assembly timing + which voice provider actually
    served the run into the telemetry.json the graph already wrote for this
    run_dir. Never raises — telemetry is diagnostic, not load-bearing."""
    import json
    import time

    filepath = os.path.join(self.run_dir, "telemetry.json")
    try:
      payload = {}
      if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
          payload = json.load(f)

      payload.setdefault("stage_durations_seconds", {})["video_assembly"] = round(time.time() - assemble_start, 2)
      payload.setdefault("providers_used", {})["voice"] = getattr(self.voice_provider, "last_used", None) or type(self.voice_provider).__name__

      with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    except Exception as e:
      print(f"[video_builder] telemetry not updated: {e}")
