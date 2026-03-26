import pulp
import logging
import asyncio
from typing import List, Dict, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from master.models.task import Task, TaskStatus
from master.models.worker import Worker, WorkerStatus
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def solve_bin_packing(tasks: List[Dict], workers: List[Dict]) -> Tuple[Dict[str, str], List[str]]:
    """
    Linear Programming Optimizer using PuLP.
    
    Model: 1-Dimensional Bin Packing Problem
    Objective: Minimize the sum of active workers `y_j`.
    Constraints: 
      1. Every task `i` must be assigned to exactly 1 worker.
      2. The sum of task weights on worker `j` cannot exceed its capacity.
      
    PERFORMANCE CONSIDERATIONS:
    --------------------------
    - NP-Hardness: Bin packing is NP-hard. As the length of tasks scales into the thousands, 
      the branch-and-bound tree of the mathematical solver expands exponentially causing extreme latency.
    - Time Limit: To combat this, we enforce a strict 10-second `timeLimit` on the C++ CBC solver.
      If it doesn't find the absolute mathematical minimum within 10s, it returns the 
      best "feasible" sub-optimal packing found before the timeout, preventing infinite deadlocks.
    - Event Loop Blocking: Mathematical solvers completely halt Python threads. We explicitly
      execute this function via `loop.run_in_executor` to offload the heavy calculations
      to a side thread, bypassing any disruption to the asyncio FastAPI traffic.
    """
    prob = pulp.LpProblem("Worker_Minimization_BinPacking", pulp.LpMinimize)

    # Decision Variables
    # w_y[j] = 1 if worker j receives >= 1 task (i.e. is active)
    w_y = pulp.LpVariable.dicts("WorkerUsed", [w["id"] for w in workers], cat="Binary")

    # t_x[i][j] = 1 if task i is assigned to worker j
    t_x = pulp.LpVariable.dicts("TaskAssigned",
                                ([t["id"] for t in tasks], [w["id"] for w in workers]),
                                cat="Binary")

    # Objective: Minimize the active server clusters to save deployment costs
    prob += pulp.lpSum([w_y[w["id"]] for w in workers]), "Minimize_Active_Workers"

    # Constraint 1: Exact assignment - No tasks left behind or duplicated
    for t in tasks:
        prob += pulp.lpSum([t_x[t["id"]][w["id"]] for w in workers]) == 1, f"Assign_{t['id']}"

    # Constraint 2: Capacity formulation - Ensure memory/slots are respected
    for w in workers:
        prob += pulp.lpSum([t_x[t["id"]][w["id"]] * t.get("cost", 1) for t in tasks]) <= w["capacity"] * w_y[w["id"]], f"Cap_{w['id']}"

    # Solve the mathematical matrix
    solver = pulp.PULP_CBC_CMD(timeLimit=10, msg=False)
    prob.solve(solver)

    assignments = {}
    used_workers = set()
        
    for t in tasks:
        for w in workers:
            if pulp.value(t_x[t["id"]][w["id"]]) == 1.0:
                assignments[t["id"]] = w["id"]
                used_workers.add(w["id"])
                
    drain_workers = [w["id"] for w in workers if w["id"] not in used_workers]
    return assignments, drain_workers


async def run_optimizer_loop(db_session_maker):
    """
    Fires the LP Optimizer every 60 seconds to rebalance the cluster, ensuring
    we are running on the absolute minimum amount of cloud instances needed.
    """
    logger.info("Initializing LP Optimization background daemon (60s tick)")
    while True:
        try:
            await asyncio.sleep(60)
            logger.info("LP Optimizer Phase Started: Reassessing global cluster topology...")
            
            async with db_session_maker() as db:
                # 1. Fetch available cluster state
                w_query = select(Worker).where(Worker.status == WorkerStatus.ACTIVE)
                w_result = await db.execute(w_query)
                active_workers = w_result.scalars().all()
                if not active_workers:
                    continue
                    
                workers_data = [{"id": str(w.id), "capacity": w.capacity} for w in active_workers]
                
                # 2. Fetch Re-assignable tasks (Currently RUNNING or PENDING)
                t_query = select(Task).where(Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]))
                t_result = await db.execute(t_query)
                target_tasks = t_result.scalars().all()
                
                if len(target_tasks) == 0:
                    continue
                    
                # Weight dynamically extracted from JSONB resource bounds
                tasks_data = [{"id": str(t.id), "cost": t.resource_reqs.get("ram_cost", 1) if t.resource_reqs else 1} for t in target_tasks]
                
                logger.info(f"Shipping {len(tasks_data)} tasks and {len(workers_data)} nodes to PuLP Solver...")
                
                # 3. Offload native threadpool solver execution
                loop = asyncio.get_running_loop()
                assignments, drain_workers = await loop.run_in_executor(
                    None, solve_bin_packing, tasks_data, workers_data
                )
                
                if not assignments:
                    logger.warning("LP Optimizer could not mathematically satisfy constraints.")
                    continue
                    
                logger.info(f"LP Strategy Accepted: Consolidating onto {len(workers_data) - len(drain_workers)} nodes.")
                
                # 4. Atomic PostgreSQL Reassignment execution
                now = datetime.now(timezone.utc)
                
                for task_id, new_worker_id in assignments.items():
                    await db.execute(
                        update(Task)
                        .where(Task.id == str(task_id))
                        .values(worker_id=str(new_worker_id), status=TaskStatus.RUNNING, updated_at=now)
                    )

                # Set drained workers to DRAINING (marks them for auto-scaling teardown)
                if drain_workers:
                    await db.execute(
                        update(Worker)
                        .where(Worker.id.in_(drain_workers))
                        .values(status=WorkerStatus.DRAINING)
                    )
                    
                await db.commit()
                logger.info("LP Rebalancing routine fully synchronized to database.")

        except Exception as e:
            logger.error(f"Critical error in LP Optimizer Loop: {e}")
