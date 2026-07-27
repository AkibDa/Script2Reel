#services/image_provider.py

import os
import torch
import threading
from typing import Protocol
from diffusers import StableDiffusionXLPipeline


class ImageProvider(Protocol):
  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    pass


class LocalSDXLProvider:
  def __init__(self, model_id="RunDiffusion/Juggernaut-X-v10"):
    self.device = "cuda" if torch.cuda.is_available() else "cpu"
    self.steps = 40 if self.device == "cuda" else 15
    self.cfg_scale = 7.0
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

  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    with self.lock:
      image = self.pipe(
        prompt=prompt,
        negative_prompt=self.negative_prompt,
        height=1216,
        width=832,
        num_inference_steps=self.steps,
        guidance_scale=self.cfg_scale
      ).images[0]

    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")
    image.save(filepath)
    return filepath
