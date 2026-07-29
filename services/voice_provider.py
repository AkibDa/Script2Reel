#services/voice_provider.py

import os
import asyncio
from typing import Protocol
from services.config_manager import VOICE_PROVIDER, dedupe_order
from services.provider_capabilities import ProviderCapabilities
from services.provider_registry import registry
from services.fallback_provider import FallbackProvider


class VoiceProvider(Protocol):
  def generate(self, text: str, run_dir: str, filename: str, voice_gender: str = "Female") -> str:
    """Synthesizes speech for `text` and returns the path to the saved audio file."""
    ...


class ElevenLabsProvider:
  capabilities = ProviderCapabilities(supports_seed=False)

  def __init__(self, api_key: str = None):
    from elevenlabs.client import ElevenLabs
    self.client = ElevenLabs(api_key=api_key or os.getenv("ELEVENLABS_API_KEY"))

  def generate(self, text: str, run_dir: str, filename: str, voice_gender: str = "Female") -> str:
    from elevenlabs import save

    target_dir = os.path.join(run_dir, "audio")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.mp3")

    voice_map = {"Male": "Adam", "Female": "Rachel"}
    target_voice = voice_map.get(voice_gender, "Rachel")
    audio = self.client.generate(text=text, voice=target_voice, model="eleven_multilingual_v2")
    save(audio, filepath)
    return filepath


class EdgeTTSProvider:
  capabilities = ProviderCapabilities(supports_seed=False)

  def generate(self, text: str, run_dir: str, filename: str, voice_gender: str = "Female") -> str:
    import edge_tts

    target_dir = os.path.join(run_dir, "audio")
    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{filename}.mp3")

    edge_voice = "en-US-GuyNeural" if voice_gender == "Male" else "en-US-JennyNeural"
    try:
      communicate = edge_tts.Communicate(text, edge_voice)
      asyncio.run(communicate.save(filepath))
    except Exception as e:
      raise RuntimeError(f"edge-tts failed: {e}")
    return filepath


registry.register("voice", "elevenlabs", lambda **kw: ElevenLabsProvider(**kw))
registry.register("voice", "edge_tts", lambda **kw: EdgeTTSProvider())


def get_voice_provider(elevenlabs_api_key: str = None) -> VoiceProvider:
  """Factory mirroring get_llm()/get_image_provider(): picks the backend
  based on the one-time env decision, wrapped in a runtime fallback so an
  ElevenLabs failure (quota, network) falls through to EdgeTTS instead of
  crashing the run. An explicit key still takes priority over the env one."""
  key = elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY")

  factories = {
    "elevenlabs": lambda: registry.create("voice", "elevenlabs", api_key=key),
    "edge_tts": lambda: registry.create("voice", "edge_tts"),
  }

  preferred = "elevenlabs" if (VOICE_PROVIDER == "elevenlabs" and key) else "edge_tts"
  order = dedupe_order([preferred, "edge_tts"])  # edge_tts never needs a key, always a safe last resort
  candidates = [(name, factories[name]) for name in order]
  return FallbackProvider(candidates)
