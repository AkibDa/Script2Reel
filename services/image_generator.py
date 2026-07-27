#services/image_generator.py

import torch
import threading
from diffusers import StableDiffusionXLPipeline
import os


class ImageGenerator:
  def __init__(self, model_id="stabilityai/stable-diffusion-xl-base-1.0"):
    self.device = "cuda" if torch.cuda.is_available() else "cpu"
    self.steps = 30 if self.device == "cuda" else 5

    self.lock = threading.Lock()

    self.pipe = StableDiffusionXLPipeline.from_pretrained(
      model_id, torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
    ).to(self.device)

    if self.device == "cuda":
      self.pipe.enable_attention_slicing()
      self.pipe.enable_model_cpu_offload()

  def generate(self, prompt: str, run_dir: str, filename: str):
    with self.lock:
      if hasattr(self.pipe.scheduler, "_step_index"):
        self.pipe.scheduler._step_index = None

      image = self.pipe(
        prompt,
        height=1216,
        width=832,
        num_inference_steps=self.steps
      ).images[0]

    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")
    image.save(filepath)
    return filepath
