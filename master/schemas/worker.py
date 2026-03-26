from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID

class WorkerRegister(BaseModel):
    capacity: int = Field(default=100, ge=1)

class WorkerHeartbeat(BaseModel):
    current_load: float = Field(default=0.0, ge=0.0)

class WorkerResponse(BaseModel):
    id: str | UUID
    status: str
    capacity: int
    current_load: float
    last_heartbeat: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
