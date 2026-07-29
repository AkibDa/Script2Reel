#services/telemetry.py
"""Records stage timings and which provider actually handled each stage
(useful once FallbackProvider is in play — the provider you *selected* isn't
always the one that *served* the request). Written to run_dir/telemetry.json
so runs can be compared later.

Usage:
    telemetry = Telemetry()
    with telemetry.track("screenplay"):
        ...
    telemetry.set_provider("image", image_provider)  # records .last_used if it's a FallbackProvider
    telemetry.save(run_dir)
"""

import os
import json
import time
from contextlib import contextmanager


class Telemetry:
  def __init__(self):
    self.stage_durations = {}
    self.providers_used = {}
    self.extra = {}
    self._run_start = time.time()

  @contextmanager
  def track(self, stage_name: str):
    start = time.time()
    try:
      yield
    finally:
      self.stage_durations[stage_name] = round(time.time() - start, 2)

  def set_provider(self, kind: str, provider) -> None:
    # FallbackProvider records which candidate actually succeeded; plain
    # providers just report their own class name.
    name = getattr(provider, "last_used", None) or type(provider).__name__
    self.providers_used[kind] = name

  def note(self, key: str, value) -> None:
    self.extra[key] = value

  def save(self, run_dir: str, filename: str = "telemetry.json") -> str:
    payload = {
      "total_duration_seconds": round(time.time() - self._run_start, 2),
      "stage_durations_seconds": self.stage_durations,
      "providers_used": self.providers_used,
      **self.extra,
    }
    filepath = os.path.join(run_dir, filename)
    os.makedirs(run_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
      json.dump(payload, f, indent=2)
    return filepath
