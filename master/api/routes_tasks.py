import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from master.core.db import get_db
from master.models.task import Task, TaskStatus
from master.schemas.task import TaskCreate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def submit_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    task_id = str(uuid.uuid4())
    new_task = Task(
        id=task_id,
        status=TaskStatus.PENDING,
        payload=task_in.payload,
        resource_reqs=task_in.resource_reqs,
        max_retries=task_in.max_retries
    )
    db.add(new_task)
    try:
        await db.commit()
        await db.refresh(new_task)
        logger.info(f"Task {task_id} successfully submitted")
        return new_task
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to submit task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task
