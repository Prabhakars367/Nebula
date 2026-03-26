import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from master.core.db import AsyncSessionLocal
from master.models.worker import Worker, WorkerStatus
from master.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

async def detect_failures_and_reassign():
    logger.info("Starting background Failure Detection Loop (10s cutoff)")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # 1. Detect dead workers (no heartbeat for 10 seconds)
                cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=10)
                
                query = select(Worker.id).where(
                    Worker.status == WorkerStatus.ACTIVE,
                    Worker.last_heartbeat < cutoff_time
                )
                result = await db.execute(query)
                dead_worker_ids = result.scalars().all()
                
                if not dead_worker_ids:
                    await asyncio.sleep(5)  # Run sweep every 5 seconds
                    continue
                    
                logger.warning(f"Detected dead workers: {dead_worker_ids}. Reassigning tasks...")
                
                # Mark workers as DEAD
                await db.execute(
                    update(Worker)
                    .where(Worker.id.in_(dead_worker_ids))
                    .values(status=WorkerStatus.DEAD)
                )
                
                # 2. Reassign tasks belonging to dead workers
                # A: Tasks that have hit max retries -> FAILED
                await db.execute(
                    update(Task)
                    .where(
                        Task.worker_id.in_(dead_worker_ids),
                        Task.status == TaskStatus.RUNNING,
                        Task.retries >= Task.max_retries
                    )
                    .values(
                        status=TaskStatus.FAILED,
                        updated_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc)
                    )
                )
                
                # B: Tasks that can be retried -> PENDING
                await db.execute(
                    update(Task)
                    .where(
                        Task.worker_id.in_(dead_worker_ids),
                        Task.status == TaskStatus.RUNNING,
                        Task.retries < Task.max_retries
                    )
                    .values(
                        status=TaskStatus.PENDING,
                        retries=Task.retries + 1,
                        worker_id=None,
                        started_at=None,
                        updated_at=datetime.now(timezone.utc)
                    )
                )
                
                await db.commit()
                logger.info(f"Successfully recovered tasks associated with {dead_worker_ids}.")

        except Exception as e:
            logger.error(f"Error in failure detection loop: {e}")
            
        await asyncio.sleep(5)
