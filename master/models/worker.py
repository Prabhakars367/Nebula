import enum
from sqlalchemy import Column, Integer, String, Enum, Float, DateTime
from sqlalchemy.sql import func
from master.models.base import Base

class WorkerStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    DEAD = "DEAD"

class Worker(Base):
    __tablename__ = "workers"

    id = Column(String, primary_key=True, index=True)
    status = Column(Enum(WorkerStatus), default=WorkerStatus.ACTIVE, nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    current_load = Column(Float, default=0.0, nullable=False) # Metric dictating busyness
    capacity = Column(Integer, default=100, nullable=False) # Max concurrent tasks it can handle
