import enum
from sqlalchemy import Column, Integer, String, Enum, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from master.models.base import Base

class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True, nullable=False)
    payload = Column(JSON, nullable=True) # The actual work data
    result = Column(JSON, nullable=True)  # Output data
    retries = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    worker_id = Column(String, ForeignKey("workers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
