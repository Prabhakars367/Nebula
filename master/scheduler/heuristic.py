import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from master.models.task import Task, TaskStatus
from master.models.worker import Worker, WorkerStatus
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

async def assign_tasks_heuristic(db: AsyncSession, batch_size: int = 500) -> int:
    """
    Real-Time Heuristic Scheduler optimized for < 100ms response bounds.
    
    Logic:
    Greedily loops over a batch of unassigned tasks, picking the available worker 
    with the lowest CPU load mathematically capable of accommodating the node in memory.
    
    COMPLEXITY ANALYSIS:
    --------------------
    Time Complexity:
      - DB Fetches: O(T + W) where T is batch_size and W is the number of active workers.
      - Allocation: O(T * W log W). Since W is relatively small in real-world clusters 
        (e.g., 50-1000 nodes), Python's Timsort handles this iteration in < 1ms.
      - Total DB Commit: O(T) batched UPDATE.
      - Overall Average Tame: O(T * W log W), well under typical 100ms bounds.
    
    Space Complexity:
      - O(T + W) for holding the task models and the mapped worker struct dictionaries.
    """
    try:
        # 1. Fetch highest-priority PENDING tasks via DB (FIFO based on created_at)
        tasks_query = select(Task).where(Task.status == TaskStatus.PENDING).order_by(Task.created_at).limit(batch_size)
        result = await db.execute(tasks_query)
        pending_tasks = result.scalars().all()

        if not pending_tasks:
            return 0  # Fast exit: No jobs to schedule

        # 2. Fetch ACTIVE workers avoiding 100% CPU lockouts
        workers_query = select(Worker).where(
            Worker.status == WorkerStatus.ACTIVE,
            Worker.current_load < 98.0  # CPU Overload threshold
        )
        w_result = await db.execute(workers_query)
        available_workers = w_result.scalars().all()

        if not available_workers:
            logger.warning("Backpressure Triggered: Zero available workers capable of accepting tasks.")
            return 0
            
        # 3. Calculate remaining capacity per worker dynamically by counting their RUNNING tasks
        count_query = select(Task.worker_id, func.count(Task.id)).where(
            Task.status == TaskStatus.RUNNING,
            Task.worker_id.in_([w.id for w in available_workers])
        ).group_by(Task.worker_id)
        
        c_result = await db.execute(count_query)
        running_counts = dict(c_result.all())  # Format: {worker_id_uuid: integer_count}
        
        # 4. Filter memory capacity & Build our local state representation for zero-latency sorting
        worker_pool = []
        for w in available_workers:
            active_count = running_counts.get(w.id, 0)
            remaining_capacity = w.capacity - active_count
            
            if remaining_capacity > 0:
                worker_pool.append({
                    "id": w.id,
                    "load": w.current_load,
                    "remaining": remaining_capacity
                })
        
        assigned_count = 0
        now = datetime.now(timezone.utc)
        
        # 5. Greedy Allocation
        for task in pending_tasks:
            if not worker_pool:
                logger.warning(f"All workers hit memory/capacity limits! Halting batch after {assigned_count} jobs.")
                break
                
            # Tie breaker: Python's builtin Timsort will consistently bubble the lowest CPU machine to index [0]
            worker_pool.sort(key=lambda x: x["load"])
            best_worker = worker_pool[0]
            
            # Map the task object locally
            task.worker_id = best_worker["id"]
            task.status = TaskStatus.RUNNING
            task.started_at = now
            task.updated_at = now
            
            assigned_count += 1
            
            # Update local node struct to prevent batch overbooking
            best_worker["remaining"] -= 1
            best_worker["load"] += 1.5  # Add a synthetic penalty modifier to CPU load to prevent dogpiling one node
            
            if best_worker["remaining"] <= 0:
                worker_pool.pop(0)  # Eject from pool if entirely full
                
        # 6. Push all batch assignments to postgres atomically
        if assigned_count > 0:
            await db.commit()
            logger.info(f"Heuristic Scheduler processed and assigned {assigned_count} tasks.")
            
        return assigned_count

    except Exception as e:
        await db.rollback()
        logger.error(f"Heuristic scheduling mathematically failed or aborted: {e}")
        return 0
