import asyncio
import time
import logging
import statistics
import json
import os
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LoadTest")

MASTER_URL = os.getenv("MASTER_URL", "http://localhost:8000")
TOTAL_TASKS = 10000
CONCURRENCY_LIMIT = 500  

async def submit_task(session: aiohttp.ClientSession, task_payload: dict, stats: list, submitted_task_ids: list):
    start_time = time.perf_counter()
    try:
        async with session.post(f"{MASTER_URL}/tasks/", json=task_payload) as response:
            status = response.status
            response_text = await response.text()
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000  # Convert to ms
            
            if status in [200, 201]:
                try:
                    data = json.loads(response_text)
                    task_id = data.get("id")
                    stats.append({"success": True, "submit_latency": latency, "task_id": task_id})
                    submitted_task_ids.append(task_id)
                except Exception:
                    stats.append({"success": False, "submit_latency": latency, "error": "JSON parse error"})
            else:
                stats.append({"success": False, "submit_latency": latency, "error": f"HTTP {status}"})
    except Exception as e:
        end_time = time.perf_counter()
        stats.append({"success": False, "submit_latency": (end_time - start_time) * 1000, "error": str(e)})

async def measure_scheduling_latency(session: aiohttp.ClientSession, task_id: str, scheduling_stats: list):
    """
    Rapidly polls a given task to see exactly when the Scheduler flips it from PENDING to RUNNING.
    """
    start_time = time.perf_counter()
    while True:
        try:
            async with session.get(f"{MASTER_URL}/tasks/{task_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") != "PENDING":
                        end_time = time.perf_counter()
                        latency_ms = (end_time - start_time) * 1000
                        scheduling_stats.append(latency_ms)
                        return
        except Exception:
            pass
        await asyncio.sleep(0.05) # Aggressive 50ms polling loop to capture exact assignment bounds

async def worker_loop(queue: asyncio.Queue, session: aiohttp.ClientSession, stats: list, submitted_ids: list):
    while True:
        task_payload = await queue.get()
        await submit_task(session, task_payload, stats, submitted_ids)
        queue.task_done()

async def simulate_load():
    logger.info(f"Initializing Load Test: {TOTAL_TASKS} Concurrent Tasks")
    
    queue = asyncio.Queue()
    for i in range(TOTAL_TASKS):
        queue.put_nowait({
            "payload": {"job_type": "simulate", "index": i},
            "resource_reqs": {"ram_cost": 1},
            "max_retries": 3
        })
        
    submission_stats = []
    submitted_task_ids = []
    scheduling_stats = []
    
    connector = aiohttp.TCPConnector(limit=CONCURRENCY_LIMIT)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Phase 1: High-concurrency task submission
        logger.info("Phase 1: Blasting 10K tasks to Master Node...")
        global_start = time.perf_counter()
        
        workers = [asyncio.create_task(worker_loop(queue, session, submission_stats, submitted_task_ids)) for _ in range(CONCURRENCY_LIMIT)]
        
        await queue.join()
        
        for w in workers:
            w.cancel()
            
        global_end = time.perf_counter()
        total_time = global_end - global_start
        throughput = TOTAL_TASKS / total_time
        
        # Phase 2: Measure Scheduling Latency (Sample size of 100 random tasks to prevent network saturation)
        import random
        sample_size = min(100, len(submitted_task_ids))
        if sample_size > 0:
            logger.info(f"Phase 2: Sampling {sample_size} tasks to measure strictly internal Scheduler Latency...")
            sample_ids = random.sample(submitted_task_ids, sample_size)
            await asyncio.gather(*(measure_scheduling_latency(session, tid, scheduling_stats) for tid in sample_ids))
        
    # Data Aggregation
    successes = [s for s in submission_stats if s["success"]]
    failures = [s for s in submission_stats if not s["success"]]
    latencies = [s["submit_latency"] for s in successes]
    
    print("\n")
    logger.info("================================================")
    logger.info("PRODUCTION NEBULA LOAD TEST RESULTS")
    logger.info("================================================")
    logger.info(f"Total Simulated:     {TOTAL_TASKS} Tasks")
    logger.info(f"API Throughput:      {throughput:.2f} tasks/second")
    logger.info(f"Total Blast Time:    {total_time:.2f} seconds")
    
    logger.info("--- API ROUNDTRIP LATENCY ---")
    if latencies:
        logger.info(f"  Average: {statistics.mean(latencies):.2f} ms")
        logger.info(f"  Median:  {statistics.median(latencies):.2f} ms")
        logger.info(f"  P95:     {statistics.quantiles(latencies, n=100)[94]:.2f} ms")
        logger.info(f"  Max:     {max(latencies):.2f} ms")
        
    logger.info("--- SCHEDULER ENGINE LATENCY ---")
    if scheduling_stats:
        logger.info(f"  Average: {statistics.mean(scheduling_stats):.2f} ms")
        logger.info(f"  Median:  {statistics.median(scheduling_stats):.2f} ms")
        logger.info("  (Note: Sub-200ms target satisfied if average < 200)")
    else:
        logger.info("  No scheduling data retrieved.")
    
    logger.info("--- RELIABILITY ---")
    logger.info(f"  Success Rate: {len(successes)}/{(TOTAL_TASKS)} ({(len(successes)/max(1,TOTAL_TASKS))*100:.2f}%)")
    logger.info(f"  Failure Rate: {len(failures)}/{(TOTAL_TASKS)} ({(len(failures)/max(1,TOTAL_TASKS))*100:.2f}%)")
    
    if failures:
        logger.warning(f"  Example Failure Reason: {failures[0].get('error')}")
        
    logger.info("================================================")

    '''
    SAMPLE EXPECTED RESULTS FORMAT:
    
    2026-03-26 [INFO] ================================================
    2026-03-26 [INFO] PRODUCTION NEBULA LOAD TEST RESULTS
    2026-03-26 [INFO] ================================================
    2026-03-26 [INFO] Total Simulated:     10000 Tasks
    2026-03-26 [INFO] API Throughput:      2450.40 tasks/second
    2026-03-26 [INFO] Total Blast Time:    4.08 seconds
    2026-03-26 [INFO] --- API ROUNDTRIP LATENCY ---
    2026-03-26 [INFO]   Average: 18.52 ms
    2026-03-26 [INFO]   Median:  15.20 ms
    2026-03-26 [INFO]   P95:     45.80 ms
    2026-03-26 [INFO]   Max:     105.32 ms
    2026-03-26 [INFO] --- SCHEDULER ENGINE LATENCY ---
    2026-03-26 [INFO]   Average: 32.50 ms
    2026-03-26 [INFO]   Median:  25.40 ms
    2026-03-26 [INFO]   (Note: Sub-200ms target satisfied if average < 200)
    2026-03-26 [INFO] --- RELIABILITY ---
    2026-03-26 [INFO]   Success Rate: 10000/10000 (100.00%)
    2026-03-26 [INFO]   Failure Rate: 0/10000 (0.00%)
    2026-03-26 [INFO] ================================================
    '''

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(simulate_load())
