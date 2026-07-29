# app.py

import streamlit as st
import os
import uuid
import traceback
from workflows.graph import reel_app
from services.video_builder import VideoBuilder
from services.scene_utils import scene_narration

st.set_page_config(page_title="Script2Reel | AI Creative Studio", layout="wide")

if "thread_id" not in st.session_state:
  st.session_state.thread_id = str(uuid.uuid4())
  st.session_state.reel_started = False

st.title("🎬 Script2Reel AI Studio")
st.markdown("Turn a single text prompt into a finished short vertical video reel.")

with st.sidebar:
  st.header("Reel Settings")
  prompt = st.text_area("What is your reel about?", "A motivational reel about discipline.")
  duration = st.selectbox("Duration (seconds)", [15, 30, 60], index=1)
  style = st.selectbox("Style", ["Motivational", "Educational", "Cinematic", "Documentary"])
  platform = st.selectbox("Platform", ["Instagram Reels", "TikTok", "YouTube Shorts"])
  voice = st.selectbox("Voice", ["Male", "Female"])

  st.divider()

  dev_mode = st.radio(
    "Generation Mode",
    ["mock", "fast", "production"],
    format_func=lambda x:
    {"mock": "🚀 Mock (0.1s)", "fast": "⚖ Fast Local (10 steps)", "production": "⭐ Production (Full + Critic)"}[x]
  )

  st.divider()
  api_key = st.text_input("Gemini API Key", type="password")
  eleven_key = st.text_input("ElevenLabs API Key (Optional)", type="password")
  bg_music = st.file_uploader("Upload Background Music (Optional)", type=["mp3", "wav"])
  duck_volume = st.slider("Background Music Volume", 0.0, 1.0, 0.1, 0.05)

  st.divider()
  if st.button("Reset / Start New Reel", use_container_width=True):
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.reel_started = False
    st.rerun()

if st.button("Generate / Resume Reel"):
  if not api_key:
    st.error("Please enter your Gemini API Key to continue.")
    st.stop()

  os.environ["GOOGLE_API_KEY"] = api_key

  run_dir = os.path.join("assets", st.session_state.thread_id)
  os.makedirs(run_dir, exist_ok=True)

  music_path = None
  if bg_music:
    music_path = os.path.join(run_dir, f"bg_{bg_music.name}")
    with open(music_path, "wb") as f:
      f.write(bg_music.getbuffer())

  config = {"configurable": {"thread_id": st.session_state.thread_id}}

  initial_state = {
    "raw_prompt": prompt,
    "duration": duration,
    "style": style,
    "platform": platform,
    "voice_gender": voice,
    "dev_mode": dev_mode,
    "run_dir": run_dir
  }

  progress_bar = st.progress(0)
  status_text = st.empty()

  try:
    status_text.text("Creative Agents are processing workflow (including images)...")

    current_state = reel_app.get_state(config)

    if not current_state.values:
      final_state = reel_app.invoke(initial_state, config=config)
    elif current_state.next:
      final_state = reel_app.invoke(None, config=config)
    else:
      final_state = current_state.values

    st.session_state.reel_started = True
    progress_bar.progress(50)

    scenes = final_state["image_prompts"]

    with st.expander("View Agent Outputs", expanded=False):
      st.json(scenes)

    vid_builder = VideoBuilder(
      run_dir=run_dir,
      elevenlabs_api_key=eleven_key,
      bg_music_path=music_path,
      duck_volume=duck_volume
    )

    for idx, scene in enumerate(scenes):
      status_text.text(f"Voice Director AI generating audio and video for scene {scene['scene']}...")
      # 1. Voice
      if not os.path.exists(os.path.join(run_dir, "audio", f"scene_{scene['scene']}.mp3")):
        narration = scene_narration(scene)
        if not narration:
          raise ValueError(f"Scene {scene['scene']} has empty narration — cannot generate voice/subtitles.")
        vid_builder.generate_voice(narration, f"scene_{scene['scene']}", voice)

      # 2. Video Clip
      video_path = os.path.join(run_dir, "videos", f"scene_{scene['scene']}.mp4")
      if not os.path.exists(video_path):
        if dev_mode == "mock":
          from services.video_provider import get_video_provider
          prov = get_video_provider("mock")
          prov.generate(scene.get("image_prompt") or scene["visual"], run_dir, f"scene_{scene['scene']}")
        else:
          img_path = os.path.join(run_dir, "images", f"scene_{scene['scene']}.png")
          if os.path.exists(img_path):
            os.makedirs(os.path.join(run_dir, "videos"), exist_ok=True)
            clip = vid_builder.apply_dynamic_motion(img_path, duration=scene['duration'])
            clip.write_videofile(video_path, fps=24, codec="libx264", logger=None)
          else:
            raise FileNotFoundError(f"Missing required image for animation: {img_path}")

      progress_bar.progress(50 + int(40 * ((idx + 1) / len(scenes))))

    status_text.text("Video Editor AI assembling the final reel...")
    output_mp4 = vid_builder.assemble(scenes)

    progress_bar.progress(100)
    status_text.text("✨ Reel Generation Complete!")

    st.video(output_mp4)

    col1, col2 = st.columns(2)

    if os.path.exists(output_mp4):
      with col1:
        with open(output_mp4, "rb") as file:
          st.download_button(label="Download MP4", data=file, file_name="final_reel.mp4", mime="video/mp4")

    subtitles_path = os.path.join(run_dir, "subtitles.srt")
    if os.path.exists(subtitles_path):
      with col2:
        with open(subtitles_path, "rb") as file:
          st.download_button(label="Download Subtitles (.srt)", data=file, file_name="subtitles.srt", mime="text/plain")

  except Exception as e:
    st.error(f"Generation failed: {str(e)}")
    traceback.print_exc()
    st.info(
      "Because checkpointing is enabled, modifying the issue (or API key) and pressing 'Generate' will attempt to resume the state from the last successful node.")
