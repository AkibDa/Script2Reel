#app.py

import streamlit as st
import os
import uuid
import traceback
from workflows.graph import reel_app
from services.image_provider import ImageProvider
from services.video_builder import VideoBuilder

st.set_page_config(page_title="Script2Reel | AI Creative Studio", layout="wide")


@st.cache_resource
def get_image_generator():
  return ImageProvider()


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
    "voice_gender": voice
  }

  progress_bar = st.progress(0)
  status_text = st.empty()

  try:
    status_text.text("Creative Agents are processing...")

    # Resume logic: pass None if we already started a reel on this thread
    final_state = reel_app.invoke(
      initial_state if not st.session_state.reel_started else None,
      config=config
    )
    st.session_state.reel_started = True
    progress_bar.progress(25)

    scenes = final_state["image_prompts"]

    with st.expander("View Agent Outputs", expanded=False):
      st.json(scenes)

    img_gen = get_image_generator()
    vid_builder = VideoBuilder(
      run_dir=run_dir,
      elevenlabs_api_key=eleven_key,
      bg_music_path=music_path,
      duck_volume=duck_volume
    )

    for idx, scene in enumerate(scenes):
      status_text.text(f"Visual Director AI generating image for scene {scene['scene']}...")
      if not os.path.exists(os.path.join(run_dir, "images", f"scene_{scene['scene']}.png")):
        img_gen.generate(scene["image_prompt"], run_dir, f"scene_{scene['scene']}")

      status_text.text(f"Voice Director AI generating audio for scene {scene['scene']}...")
      if not os.path.exists(os.path.join(run_dir, "audio", f"scene_{scene['scene']}.mp3")):
        vid_builder.generate_voice(scene["voice"], f"scene_{scene['scene']}", voice)

      progress_bar.progress(25 + int(50 * ((idx + 1) / len(scenes))))

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
