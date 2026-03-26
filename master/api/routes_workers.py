import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from master.core.db import get_db
from master.models.worker import Worker, WorkerStatus
from master.schemas.worker import WorkerRegister, WorkerHeartbeat, WorkerResponse

router = APIRouter(prefix="/workers", tags=["Workers"])
logger = logging.getLogger(__name__)

@router.post("/register", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
async def register_worker(worker_in: WorkerRegister, db: AsyncSession = Depends(get_db)):
    worker_id = str(uuid.uuid4())
    new_worker = Worker(
        id=worker_id,
        status=WorkerStatus.ACTIVE,
        capacity=worker_in.capacity,
        current_load=0.0
    )
    db.add(new_worker)
    try:
        await db.commit()
        await db.refresh(new_worker)
        logger.info(f"Worker {worker_id} successfully registered")
        return new_worker
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to register worker: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{worker_id}/heartbeat")
async def worker_heartbeat(worker_id: str, heartbeat_in: WorkerHeartbeat, db: AsyncSession = Depends(get_db)):
    query = select(Worker).where(Worker.id == worker_id)
    result = await db.execute(query)
    worker = result.scalar_one_or_none()
    
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
        
    worker.current_load = heartbeat_in.current_load
    worker.last_heartbeat = datetime.now(timezone.utc)
    
    # If the worker was considered DEAD, revive it upon successful heartbeat validation
    if worker.status == WorkerStatus.DEAD:
        worker.status = WorkerStatus.ACTIVE

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update worker heartbeat for {worker_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
    return {"status": "ok", "worker_id": worker_id}
