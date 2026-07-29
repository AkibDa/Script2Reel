#services/fallback_provider.py
"""Wraps an ordered list of candidate providers that all share a common
`generate(...)` signature (ImageProvider / VoiceProvider / VideoProvider).

Candidates are given as (name, factory) pairs and constructed lazily —
the primary is built on first use, and a fallback is only ever constructed
if an earlier candidate actually fails, so we don't eagerly load a 6GB SDXL
model just to have it sit unused behind OpenAI, for instance.

    OpenAI quota exceeded
        -> logs it, tries the next candidate (e.g. local SDXL)
        -> logs it, tries the next
        -> raises only if every candidate has failed
"""

from typing import Any, Callable, List, Tuple


class FallbackProvider:
  def __init__(self, candidates: List[Tuple[str, Callable[[], Any]]]):
    if not candidates:
      raise ValueError("FallbackProvider needs at least one candidate")
    self.candidates = candidates
    self._instances = {}
    self.last_used = None
    self.capabilities = None

  def _get_instance(self, name: str, factory: Callable[[], Any]) -> Any:
    if name not in self._instances:
      self._instances[name] = factory()
    return self._instances[name]

  def generate(self, *args, **kwargs):
    errors = {}
    for name, factory in self.candidates:
      try:
        provider = self._get_instance(name, factory)
        result = provider.generate(*args, **kwargs)
        self.last_used = name
        self.capabilities = getattr(provider, "capabilities", None)
        return result
      except Exception as e:
        errors[name] = str(e)
        print(f"[fallback] '{name}' failed at runtime ({e}) — trying next provider...")
    raise RuntimeError(f"All providers failed. Tried: {errors}")
