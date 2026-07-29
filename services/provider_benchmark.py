#services/provider_benchmark.py
"""Rough, hand-maintained benchmark numbers for the LLM backends this project
supports, so the app can answer "which provider is fastest/cheapest/best"
instead of that being hardcoded into provider-selection logic.

These are approximate and meant for relative comparison during development,
not a pricing guarantee — update them as models/pricing change.
"""

from dataclasses import dataclass
from typing import Dict, Literal, Optional

Criterion = Literal["fastest", "cheapest", "highest_quality"]


@dataclass(frozen=True)
class BenchmarkEntry:
  provider: str
  model: str
  latency_seconds: float   # rough time-to-first-full-response for a typical scene-planning call
  cost_tier: int           # 1 = cheapest ... higher = pricier, relative ordering only
  quality_score: int       # 1-5, subjective/relative


LLM_BENCHMARKS: Dict[str, BenchmarkEntry] = {
  "gemini": BenchmarkEntry(provider="gemini", model="gemini-flash-lite-latest", latency_seconds=2.1, cost_tier=1, quality_score=3),
  "openai": BenchmarkEntry(provider="openai", model="gpt-4o-mini", latency_seconds=3.8, cost_tier=2, quality_score=4),
}


def recommend(criterion: Criterion, table: Dict[str, BenchmarkEntry] = None) -> Optional[str]:
  """Returns the provider key that best satisfies `criterion`, or None if the
  table is empty. Purely informational right now — config_manager logs the
  recommendation at startup but still lets the env-based auto-selection (key
  presence / hardware) make the actual call, since 'fastest on paper' isn't
  useful if that provider's key isn't even configured."""
  table = table or LLM_BENCHMARKS
  if not table:
    return None

  if criterion == "fastest":
    return min(table, key=lambda k: table[k].latency_seconds)
  if criterion == "cheapest":
    return min(table, key=lambda k: table[k].cost_tier)
  if criterion == "highest_quality":
    return max(table, key=lambda k: table[k].quality_score)
  raise ValueError(f"Unknown criterion: {criterion}")
