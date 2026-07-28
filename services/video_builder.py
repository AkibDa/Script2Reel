#services/video_builder.py

import os
import pysrt
import random
from moviepy import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, CompositeVideoClip
from moviepy.video.fx import Resize, CrossFadeIn
from moviepy.audio.fx import MultiplyVolume
from elevenlabs.client import ElevenLabs
from elevenlabs import save
from gtts import gTTS
from services.scene_utils import scene_narration


class VideoBuilder:
  def __init__(self, run_dir: str, elevenlabs_api_key: str = None, bg_music_path: str = None, duck_volume: float = 0.1):
    self.run_dir = run_dir
    self.tts_client = ElevenLabs(api_key=elevenlabs_api_key) if elevenlabs_api_key else None
    self.bg_music_path = bg_music_path
    self.duck_volume = duck_volume

  def generate_voice(self, text: str, filename: str, voice_gender: str) -> str:
    text = (text or "").strip()
    if not text or text.lower() in ("none", "null"):
      raise ValueError(f"Cannot generate voice for '{filename}': narration is empty.")

    target_dir = os.path.join(self.run_dir, "audio")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.mp3")

    if self.tts_client:
      voice_map = {"Male": "Adam", "Female": "Rachel"}
      target_voice = voice_map.get(voice_gender, "Rachel")
      audio = self.tts_client.generate(text=text, voice=target_voice, model="eleven_multilingual_v2")
      save(audio, filepath)
    else:
      try:
        tts = gTTS(text=text, lang='en')
        tts.save(filepath)
      except Exception as e:
        raise RuntimeError(f"Fallback gTTS failed (requires internet connection): {e}")

    return filepath

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
    """Creates an automatic blurred background for images that don't fit 9:16 natively."""
    from PIL import Image, ImageFilter
    import numpy as np

    img = Image.open(image_path).convert('RGB')
    img = img.resize((1080, int(1080 * img.height / img.width)), Image.LANCZOS)
    img = img.crop((0, (img.height - 1920) // 2, 1080, (img.height + 1920) // 2))
    img = img.filter(ImageFilter.GaussianBlur(radius=30))

    bg_clip = ImageClip(np.array(img)).with_duration(duration)
    return bg_clip

  def apply_dynamic_motion(self, image_path: str, duration: int, zoom_factor: float = 1.15) -> ImageClip:
    motion_type = random.choice(["zoom_in", "pan_right", "pan_left", "pan_up", "pan_down"])

    base_clip = ImageClip(image_path).with_duration(duration)

    if base_clip.w / base_clip.h > 1080 / 1920:
      bg_clip = self._create_blurred_background(image_path, duration)
      fg_clip = base_clip.with_effects([Resize(width=1080)])
      fg_clip = fg_clip.with_position("center")
      clip = CompositeVideoClip([bg_clip, fg_clip])
    else:
      clip = base_clip.with_effects([Resize(height=1920)])
      if clip.w < 1080:
        clip = clip.with_effects([Resize(width=1080)])

    w, h = clip.w, clip.h
    target_w, target_h = 1080, 1920

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
    video_clips = []
    transition_duration = 0.3

    for scene in scene_data:
      audio_path = os.path.join(self.run_dir, "audio", f"scene_{scene['scene']}.mp3")
      if os.path.exists(audio_path):
        a_clip = AudioFileClip(audio_path)
        scene['duration'] = a_clip.duration + transition_duration

    self.generate_subtitles(scene_data)

    for i, scene in enumerate(scene_data):
      img_path = os.path.join(self.run_dir, "images", f"scene_{scene['scene']}.png")
      audio_path = os.path.join(self.run_dir, "audio", f"scene_{scene['scene']}.mp3")

      if not os.path.exists(img_path):
        raise FileNotFoundError(f"Missing required image for assembly: {img_path}")

      v_clip = self.apply_dynamic_motion(img_path, scene['duration'])

      if os.path.exists(audio_path):
        a_clip = AudioFileClip(audio_path)
        v_clip = v_clip.with_audio(a_clip)

      if i > 0:
        v_clip = v_clip.with_effects([CrossFadeIn(transition_duration)])

      video_clips.append(v_clip)

    final_video = concatenate_videoclips(
      video_clips,
      padding=-transition_duration,
      method="compose"
    )

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
    return output_path
