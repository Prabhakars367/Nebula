from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class TaskCreate(BaseModel):
    payload: Dict[str, Any]
    resource_reqs: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=3, ge=0, le=10)

class TaskResponse(BaseModel):
    id: str | UUID
    status: str
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    retries: int
    max_retries: int
    worker_id: Optional[str | UUID] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
