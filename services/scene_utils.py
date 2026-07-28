"""Helpers for scene dict fields shared by graph + video assembly."""

from __future__ import annotations

from typing import Any, Dict


def scene_narration(scene: Dict[str, Any]) -> str:
  """Full spoken line for TTS/subtitles. Prefers `narration`, falls back to legacy `voice`."""
  raw = scene.get("narration")
  if raw is None or (isinstance(raw, str) and not raw.strip()):
    raw = scene.get("voice")
  if raw is None:
    return ""
  text = str(raw).strip()
  if text.lower() in ("none", "null", "n/a", "na"):
    return ""
  return text
