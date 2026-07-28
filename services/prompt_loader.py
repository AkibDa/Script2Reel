#services/prompt_loader.py

import os
from functools import lru_cache


@lru_cache(maxsize=32)
def load_prompt(agent_name: str) -> str:
  """Loads a markdown prompt specification from the prompts directory."""
  filepath = os.path.join("prompts", f"{agent_name}.md")
  if not os.path.exists(filepath):
    raise FileNotFoundError(f"Cannot find prompt specification: {filepath}")

  with open(filepath, "r", encoding="utf-8") as f:
    return f.read()