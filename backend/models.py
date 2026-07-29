from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class JobCreateResponse(BaseModel):
  job_id: str


class JobStatusResponse(BaseModel):
  job_id: str
  status: Literal["queued", "running", "done", "failed"]
  stage: str = ""
  progress: int = Field(default=0, ge=0, le=100)
  error: Optional[str] = None
  agent_status: Optional[Dict[str, str]] = None


class AgentOutputsResponse(BaseModel):
  job_id: str
  scenes: List[Dict[str, Any]]
