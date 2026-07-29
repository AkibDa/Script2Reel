#services/image_provider.py

import os
import torch
import threading
from typing import Protocol
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageDraw
from services.config_manager import IMAGE_PROVIDER, dedupe_order
from services.provider_capabilities import ProviderCapabilities
from services.provider_registry import registry
from services.fallback_provider import FallbackProvider


class ImageProvider(Protocol):
  def generate(self, prompt: str, run_dir: str, filename: str) -> str:
    pass


class MockImageProvider:
  """Generates a fast placeholder image for development testing."""

  capabilities = ProviderCapabilities(max_resolution=(512, 512))

  def generate(self, prompt: str, run_dir: str, filename: str, **kwargs) -> str:
    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")

    img = Image.new('RGB', (512, 512), color=(45, 45, 45))
    d = ImageDraw.Draw(img)
    d.text((20, 256), f"MOCK IMAGE\nPrompt: {prompt[:40]}...", fill=(255, 255, 255))
    img.save(filepath)

    return filepath


class LocalSDXLProvider:
  def __init__(self, model_id="RunDiffusion/Juggernaut-X-v10", steps=40, resolution=(1344, 768)):
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

    self.capabilities = ProviderCapabilities(supports_seed=True, max_resolution=resolution)

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


class OpenAIImageProvider:
  """Cloud fallback used when there's no local GPU but an OpenAI key is available."""

  capabilities = ProviderCapabilities(supports_seed=False, max_resolution=(1024, 1024))

  def __init__(self, model: str = "gpt-image-1"):
    from openai import OpenAI
    self.client = OpenAI()
    self.model = model

  def generate(self, prompt: str, run_dir: str, filename: str, **kwargs) -> str:
    import base64
    target_dir = os.path.join(run_dir, "images")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.png")

    result = self.client.images.generate(model=self.model, prompt=prompt, size="1024x1024")
    image_bytes = base64.b64decode(result.data[0].b64_json)
    with open(filepath, "wb") as f:
      f.write(image_bytes)
    return filepath


registry.register("image", "mock", lambda **kw: MockImageProvider())
registry.register("image", "openai", lambda **kw: OpenAIImageProvider(**kw))
registry.register("image", "local_sdxl", lambda **kw: LocalSDXLProvider(**kw))


def get_image_provider(mode: str) -> ImageProvider:
  """Factory to inject the correct provider based on dev mode + the one-time
  env decision, wrapped in a runtime fallback chain: if the selected provider
  fails mid-run (e.g. an OpenAI quota error), the next candidate is tried
  automatically instead of crashing the pipeline."""
  if mode == "mock":
    return registry.create("image", "mock")

  sdxl_kwargs = {"steps": 10, "resolution": (512, 512)} if mode == "fast" else {"steps": 40, "resolution": (832, 1216)}
  factories = {
    "local_sdxl": lambda: registry.create("image", "local_sdxl", **sdxl_kwargs),
    "openai": lambda: registry.create("image", "openai"),
    "mock": lambda: registry.create("image", "mock"),
  }

  order = dedupe_order([IMAGE_PROVIDER, "local_sdxl", "openai", "mock"])
  candidates = [(name, factories[name]) for name in order if name in factories]
  return FallbackProvider(candidates)
