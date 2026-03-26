import asyncio
import logging
from master.core.db import AsyncSessionLocal
from master.scheduler.heuristic import assign_tasks_heuristic

logger = logging.getLogger(__name__)

async def scheduling_daemon():
    """
    Boundless background loop driving the scheduling engines.
    """
    logger.info("Initializing Heuristic Scheduler Pipeline...")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Dispatch up to 500 tasks per tick
                assigned = await assign_tasks_heuristic(db, batch_size=500)
                
                # Dynamic Polling Speed: Back-off physically executing database queries 
                # to save IOPS if the PENDING queue is currently empty.
                if assigned == 0:
                    await asyncio.sleep(0.5) 
                else:
                    await asyncio.sleep(0.01) # Poll aggressively while chewing through a large queue
                    
        except Exception as e:
            logger.error(f"Scheduler daemon crashed, recovering... {e}")
            await asyncio.sleep(2)
