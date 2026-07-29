#services/provider_capabilities.py


from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ProviderCapabilities:
  supports_json: bool = False
  supports_vision: bool = False
  supports_video: bool = False
  supports_streaming: bool = False
  supports_seed: bool = False
  max_resolution: Optional[Tuple[int, int]] = None
