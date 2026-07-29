#services/video_provider.py
"""Per-scene animation generation (text -> short video clip).

Kept separate from image_provider.py (still images) and from
video_builder.py (which assembles the already-generated clips, audio, and
subtitles into the final reel) — three different responsibilities that were
previously tangled together.
"""

import os
from typing import Protocol
from PIL import Image, ImageDraw
from services.config_manager import VIDEO_PROVIDER, dedupe_order
from services.provider_capabilities import ProviderCapabilities
from services.provider_registry import registry
from services.fallback_provider import FallbackProvider


class VideoProvider(Protocol):
  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    """Generates a short clip for `prompt` and returns the path to the saved video file."""
    ...


class MockVideoProvider:
  """Fast placeholder clip for development testing, mirrors MockImageProvider."""

  capabilities = ProviderCapabilities(supports_video=True, max_resolution=(512, 512))

  def generate(self, prompt: str, run_dir: str, filename: str, **kwargs) -> str:
    target_dir = os.path.join(run_dir, "videos")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.mp4")

    from moviepy import ImageClip

    img = Image.new('RGB', (512, 512), color=(45, 45, 45))
    d = ImageDraw.Draw(img)
    d.text((20, 256), f"MOCK VIDEO\nPrompt: {prompt[:40]}...", fill=(255, 255, 255))

    clip = ImageClip(__import__("numpy").array(img)).with_duration(2)
    clip.write_videofile(filepath, fps=8, codec="libx264", logger=None)
    return filepath


class LocalVideoProvider:
  capabilities = ProviderCapabilities(supports_video=True, max_resolution=(576, 320))

  def __init__(self, model_id="cerspense/zeroscope_v2_576w"):
    import torch
    from diffusers import TextToVideoSDPipeline

    self.device = "cuda" if torch.cuda.is_available() else "cpu"
    self.pipe = TextToVideoSDPipeline.from_pretrained(
      model_id, torch_dtype=torch.float16
    ).to(self.device)
    self.pipe.enable_model_cpu_offload()

  def generate(self, prompt: str, run_dir: str, filename: str, **kwargs) -> str:
    import torch
    from diffusers.utils import export_to_video

    target_dir = os.path.join(run_dir, "videos")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.mp4")

    with torch.no_grad():
      video_frames = self.pipe(prompt, num_inference_steps=25, num_frames=24).frames[0]

    export_to_video(video_frames, filepath, fps=8)
    return filepath


registry.register("video", "local", lambda **kw: LocalVideoProvider(**kw))
registry.register("video", "mock", lambda **kw: MockVideoProvider())


def get_video_provider(mode: str = "production") -> VideoProvider:
  """Factory mirroring get_image_provider(): dev-mode override first, then
  the one-time env/GPU decision, wrapped in a runtime fallback chain so a
  model-loading or inference failure falls back to the mock clip generator
  instead of crashing the run."""
  if mode == "mock":
    return registry.create("video", "mock")

  factories = {
    "local": lambda: registry.create("video", "local"),
    "mock": lambda: registry.create("video", "mock"),
  }
  if VIDEO_PROVIDER == "mock":
    order = dedupe_order(["local", "mock"])
  else:
    order = dedupe_order([VIDEO_PROVIDER, "local", "mock"])
  candidates = [(name, factories[name]) for name in order if name in factories]
  return FallbackProvider(candidates)
