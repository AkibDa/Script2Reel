#services/provider_registry.py
"""Central place providers get registered under a (kind, name) key, so
`get_image_provider()` / `get_voice_provider()` / etc. call `registry.create(...)`
instead of growing another if/elif chain every time a new backend is added.

This replaces the earlier draft of this file, which referenced a
`services.voice_provider` / `services.config_manager.CapabilityChecker` /
`OpenAIProvider` / `MockLLMProvider` that never existed. Those pieces are now
real (see voice_provider.py, video_provider.py, config_manager.py), wired
through this registry instead.

Usage (in a provider module, at import time):
    from services.provider_registry import registry
    registry.register("image", "openai", lambda **kw: OpenAIImageProvider(**kw))

Usage (in a factory function):
    provider = registry.create("image", "openai")
"""

from typing import Callable, Dict, List, Tuple, Any


class ProviderRegistry:
  def __init__(self):
    self._factories: Dict[Tuple[str, str], Callable[..., Any]] = {}

  def register(self, kind: str, name: str, factory: Callable[..., Any]) -> None:
    self._factories[(kind, name)] = factory

  def available(self, kind: str) -> List[str]:
    return [name for (k, name) in self._factories if k == kind]

  def create(self, kind: str, name: str, **kwargs) -> Any:
    key = (kind, name)
    if key not in self._factories:
      raise KeyError(f"No '{name}' provider registered for '{kind}'. Available: {self.available(kind)}")
    return self._factories[key](**kwargs)


registry = ProviderRegistry()
