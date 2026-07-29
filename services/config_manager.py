#services/config_manager.py
"""
Decides which provider to use for each pipeline stage by checking the
environment exactly once (at import time, since Python only executes a
module's top level the first time it's imported — every later
`from services.config_manager import LLM_PROVIDER` just reuses the cached
result).

Override any decision explicitly via env vars:
    LLM_PROVIDER=openai|gemini
    IMAGE_PROVIDER=openai|local_sdxl|mock
    VOICE_PROVIDER=elevenlabs|edge_tts
    VIDEO_PROVIDER=local|mock

Otherwise it auto-picks based on which API keys / hardware are present.

Module-level constants (LLM_PROVIDER, IMAGE_PROVIDER, ...) are kept for
existing call sites. `CONFIG` bundles the same decisions into one
PipelineConfig object, which is the preferred way to thread settings through
new code (easier to mock in tests than importing globals).
"""

import os
from dataclasses import dataclass, field
from typing import Dict


try:
  import torch
  _GPU_AVAILABLE = torch.cuda.is_available()
except Exception:
  _GPU_AVAILABLE = False

_HAS_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
_HAS_GEMINI = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
_HAS_ELEVENLABS = bool(os.getenv("ELEVENLABS_API_KEY"))
_HAS_FLUX = bool(os.getenv("FLUX_API_KEY"))  # not implemented yet, tracked for the matrix/future provider

# Public aliases — other modules building fallback chains need to know what's
# actually usable, not just what's currently selected.
HAS_OPENAI = _HAS_OPENAI
HAS_GEMINI = _HAS_GEMINI
HAS_ELEVENLABS = _HAS_ELEVENLABS
HAS_GPU = _GPU_AVAILABLE

# --- Screenplay / structured-output LLM ---
_llm_override = os.getenv("LLM_PROVIDER", "").lower()
if _llm_override:
  LLM_PROVIDER = _llm_override
elif _HAS_GEMINI:
  LLM_PROVIDER = "gemini"
elif _HAS_OPENAI:
  LLM_PROVIDER = "openai"
else:
  raise RuntimeError(
    "No LLM API key found. Set GOOGLE_API_KEY (or GEMINI_API_KEY) or OPENAI_API_KEY."
  )

# --- Image generation ---
_image_override = os.getenv("IMAGE_PROVIDER", "").lower()
if _image_override:
  IMAGE_PROVIDER = _image_override
elif _GPU_AVAILABLE:
  IMAGE_PROVIDER = "local_sdxl"
elif _HAS_OPENAI:
  IMAGE_PROVIDER = "openai"
else:
  IMAGE_PROVIDER = "mock"

# --- Voice / TTS ---
_voice_override = os.getenv("VOICE_PROVIDER", "").lower()
if _voice_override:
  VOICE_PROVIDER = _voice_override
elif _HAS_ELEVENLABS:
  VOICE_PROVIDER = "elevenlabs"
else:
  VOICE_PROVIDER = "edge_tts"

# --- Per-scene animation / video generation ---
_video_override = os.getenv("VIDEO_PROVIDER", "").lower()
if _video_override:
  VIDEO_PROVIDER = _video_override
elif _GPU_AVAILABLE:
  VIDEO_PROVIDER = "local"
else:
  VIDEO_PROVIDER = "mock"


@dataclass(frozen=True)
class RenderSettings:
  fps: int = 24
  width: int = 1920
  height: int = 1080


@dataclass(frozen=True)
class PipelineConfig:
  """Single object bundling every provider decision + render settings.

  Prefer threading this through new code instead of importing the module
  globals directly — it's the same information, but easy to construct a
  custom instance of for tests instead of monkeypatching env vars.
  """
  llm_provider: str
  image_provider: str
  voice_provider: str
  video_provider: str
  render_settings: RenderSettings = field(default_factory=RenderSettings)


CONFIG = PipelineConfig(
  llm_provider=LLM_PROVIDER,
  image_provider=IMAGE_PROVIDER,
  voice_provider=VOICE_PROVIDER,
  video_provider=VIDEO_PROVIDER,
)


def dedupe_order(names) -> list:
  """Keeps first occurrence only, preserving order — used when building a
  fallback chain like [selected, ...defaults] where `selected` might already
  be one of the defaults."""
  seen = set()
  result = []
  for n in names:
    if n and n not in seen:
      seen.add(n)
      result.append(n)
  return result


def capability_matrix() -> Dict[str, bool]:
  """What's actually available to pick from, independent of what got selected."""
  return {
    "Gemini": _HAS_GEMINI,
    "OpenAI": _HAS_OPENAI,
    "Local SDXL": _GPU_AVAILABLE,
    "FLUX": _HAS_FLUX,
    "Local Video (zeroscope)": _GPU_AVAILABLE,
    "EdgeTTS": True,  # no key required
    "ElevenLabs": _HAS_ELEVENLABS,
  }


def health_check() -> Dict[str, str]:
  """Best-effort startup check. This deliberately avoids slow/costly network
  calls (e.g. an actual Gemini/OpenAI request) — it confirms what it can
  cheaply confirm (key present, GPU visible, local Ollama server reachable)
  and is upfront about the rest."""
  results = {}

  results["Gemini"] = "key present" if _HAS_GEMINI else "no key (GOOGLE_API_KEY/GEMINI_API_KEY)"
  results["OpenAI"] = "key present" if _HAS_OPENAI else "no key (OPENAI_API_KEY)"
  results["ElevenLabs"] = "key present" if _HAS_ELEVENLABS else "no key (ELEVENLABS_API_KEY) — will use EdgeTTS"
  results["Local SDXL / Video"] = "GPU detected" if _GPU_AVAILABLE else "no CUDA GPU — will use CPU or a cloud/mock fallback"

  try:
    import requests
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    requests.get(ollama_host, timeout=0.3)
    results["Ollama"] = "server reachable"
  except Exception:
    results["Ollama"] = "not running (optional)"

  return results


def print_summary():
  print("\n===================== CHECKING PROVIDERS =====================")
  for name, status in health_check().items():
    ok = "reachable" in status or "present" in status or "detected" in status
    mark = "\u2713" if ok else "\u2717"
    print(f" {mark} {name}: {status}")

  print("\n===================== AVAILABLE PROVIDERS =====================")
  for name, available in capability_matrix().items():
    mark = "\u2713" if available else "\u2717"
    print(f" {mark} {name}")

  print("\n----------------------- SELECTED -----------------------")
  print(f" LLM   : {CONFIG.llm_provider}")
  print(f" Image : {CONFIG.image_provider}")
  print(f" Voice : {CONFIG.voice_provider}")
  print(f" Video : {CONFIG.video_provider}")

  try:
    from services.provider_benchmark import recommend
    print(f"\n (benchmark table would suggest: fastest={recommend('fastest')}, "
          f"cheapest={recommend('cheapest')}, highest_quality={recommend('highest_quality')} — "
          f"informational only, selection above is still env/hardware-driven)")
  except Exception:
    pass

  print("=================================================================\n")


print_summary()
