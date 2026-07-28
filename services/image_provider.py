#services/image_provider.py

import os
import torch
import threading
from typing import Protocol
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageDraw


class ImageProvider(Protocol):
  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    pass


class MockImageProvider:
  """Generates a fast placeholder image for development testing."""

  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")

    img = Image.new('RGB', (512, 512), color=(45, 45, 45))
    d = ImageDraw.Draw(img)
    d.text((20, 256), f"MOCK IMAGE\nPrompt: {prompt[:40]}...", fill=(255, 255, 255))
    img.save(filepath)

    return filepath


class LocalSDXLProvider:
  def __init__(self, model_id="RunDiffusion/Juggernaut-X-v10", steps=40, resolution=(832, 1216)):
    self.device = "cuda" if torch.cuda.is_available() else "cpu"
    self.steps = steps if self.device == "cuda" else 15
    self.cfg_scale = 7.0
    self.width, self.height = resolution
    self.lock = threading.Lock()

    self.negative_prompt = (
      "blurry, low quality, text, watermark, logo, deformed, "
      "extra fingers, bad anatomy, cropped, duplicate, abstract, "
      "cyberpunk, distorted, floating objects, noise, messy"
    )

    self.pipe = StableDiffusionXLPipeline.from_pretrained(
      model_id,
      torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
    ).to(self.device)

    if self.device == "cuda":
      self.pipe.enable_attention_slicing()
      self.pipe.enable_model_cpu_offload()


  def generate(self, prompt: str, run_dir: str, filename: str, **kwargs) -> str:
    steps = kwargs.get("steps", self.steps)
    cfg_scale = kwargs.get("cfg_scale", self.cfg_scale)
    negative_prompt = kwargs.get("negative_prompt", self.negative_prompt)
    seed = kwargs.get("seed", None)

    generator = None
    if seed is not None:
      generator = torch.Generator(device=self.device).manual_seed(seed)

    with self.lock:
      image = self.pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        height=self.height,
        width=self.width,
        num_inference_steps=steps,
        guidance_scale=cfg_scale,
        generator=generator
      ).images[0]

    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")
    image.save(filepath)
    return filepath


def get_image_provider(mode: str) -> ImageProvider:
  """Factory to inject the correct provider based on development mode."""
  if mode == "mock":
    return MockImageProvider()
  elif mode == "fast":
    return LocalSDXLProvider(steps=10, resolution=(512, 512))
  else:
    return LocalSDXLProvider(steps=40, resolution=(832, 1216))
