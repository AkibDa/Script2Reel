#services/video_builder.py

import os
import pysrt
from moviepy import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from moviepy.video.fx import Crop, Resize
from moviepy.audio.fx import MultiplyVolume
from elevenlabs.client import ElevenLabs
from elevenlabs import save
from gtts import gTTS


class VideoBuilder:
  def __init__(self, run_dir: str, elevenlabs_api_key: str = None, bg_music_path: str = None, duck_volume: float = 0.1):
    self.run_dir = run_dir
    self.tts_client = ElevenLabs(api_key=elevenlabs_api_key) if elevenlabs_api_key else None
    self.bg_music_path = bg_music_path
    self.duck_volume = duck_volume

  def generate_voice(self, text: str, filename: str, voice_gender: str) -> str:
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
      start_time = current_time_sec
      end_time = current_time_sec + scene['duration']

      sub = pysrt.SubRipItem(
        index=scene['scene'],
        start=pysrt.SubRipTime(seconds=start_time),
        end=pysrt.SubRipTime(seconds=end_time),
        text=scene['voice']
      )
      subs.append(sub)
      current_time_sec = end_time

    subs.save(filepath, encoding='utf-8')
    return filepath

  def apply_ken_burns(self, image_path: str, duration: int, zoom_factor: float = 1.1) -> ImageClip:
    clip = ImageClip(image_path).with_duration(duration)

    # Scale to cover target dimensions before cropping
    clip = clip.with_effects([Resize(height=1920)])
    if clip.w < 1080:
      clip = clip.with_effects([Resize(width=1080)])

    clip = clip.with_effects([Resize(lambda t: 1 + (zoom_factor - 1) * t / duration)])
    clip = clip.with_effects([Crop(x_center=clip.w / 2, y_center=clip.h / 2, width=1080, height=1920)])
    return clip

  def assemble(self, scene_data: list, output_filename: str = "final_reel.mp4"):
    video_clips = []

    self.generate_subtitles(scene_data)

    for scene in scene_data:
      img_path = os.path.join(self.run_dir, "images", f"scene_{scene['scene']}.png")
      audio_path = os.path.join(self.run_dir, "audio", f"scene_{scene['scene']}.mp3")

      if not os.path.exists(img_path):
        raise FileNotFoundError(f"Missing required image for assembly: {img_path}")

      v_clip = self.apply_ken_burns(img_path, scene['duration'])

      if os.path.exists(audio_path):
        a_clip = AudioFileClip(audio_path)
        v_clip = v_clip.with_audio(a_clip)

      video_clips.append(v_clip)

    final_video = concatenate_videoclips(video_clips, method="compose")

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
