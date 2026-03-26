"""
Project Nebula: Chaos Engineering Monkey

FAILURE SCENARIOS:
1. Sudden Container Death (`docker kill`):
   - Description: Instantly destroys a worker container process.
   - Expected Outcome: The Master Node's `worker_monitor` daemon triggers after 10 
     seconds of missed heartbeats. The worker is marked DEAD. Its `RUNNING` tasks are 
     rolled back to `PENDING` (and retries are bumped). The Heuristic or LP Scheduler
     instantly picks up the tasks and assigns them to the surviving cluster nodes.

2. Network Partitions / Blackouts (`docker pause`):
   - Description: Freezes the container's execution mimicking a severed ethernet cable.
     The worker program never naturally dies, but it cannot ping the Master.
   - Expected Outcome: Identical DB-level recovery to sudden death. When unpaused 
     (network restored), the Master's heartbeat logic will see the worker re-emerge and 
     gracefully transition it back from DEAD to ACTIVE, allowing it to take new tasks again.
"""

import time
import subprocess
import logging
import random
import sys

# Configure logging matching Nebula standards
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] CHAOS: %(message)s")
logger = logging.getLogger("ChaosMonkey")

def run_cmd(cmd: str):
    logger.debug(f"Executing: {cmd}")
    subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_running_workers():
    # Safely fetches all docker standard output containing active worker container IDs
    result = subprocess.run("docker compose ps -q worker", shell=True, capture_output=True, text=True)
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def inject_sudden_death():
    try:
        workers = get_running_workers()
        if not workers or workers == [""]:
            logger.warning("No worker instances detected. Are they running?")
            return
        
        target = random.choice(workers)
        logger.warning(f"SCENARIO 1: Brutally killing worker container [{target[:8]}]")
        run_cmd(f"docker kill {target}")
    except Exception as e:
        logger.error(f"Kill command injection failed: {e}")

def inject_network_partition():
    try:
        workers = get_running_workers()
        if not workers or workers == [""]:
            return
            
        target = random.choice(workers)
        logger.warning(f"SCENARIO 2: Simulating network blackout (PAUSE) on worker [{target[:8]}]")
        run_cmd(f"docker pause {target}")
        
        # We hold the partition longer than the master's 10-second failure cutoff
        blackout_duration = 15 
        logger.info(f"Worker [{target[:8]}] is severed from network. Holding for {blackout_duration}s...")
        time.sleep(blackout_duration)
        
        logger.info(f"Restoring network for worker [{target[:8]}]")
        run_cmd(f"docker unpause {target}")
    except Exception as e:
        logger.error(f"Network simulation injection failed: {e}")

def verify_system_stability():
    logger.info("--- MANUAL VERIFICATION STEPS ---")
    logger.info("> Check master node logs. You should see: 'Detected dead workers... Reassigning tasks'.")
    logger.info("> The Load Generator metric for 'Reliability' should still read 100.00% Success Rate.")
    logger.info("> The LP Optimizer should consolidate active tasks onto the surviving containers within 60s.")

if __name__ == "__main__":
    logger.info("Initializing Nebula Chaos Engine...")
    logger.info("Warning: This script assumes 'docker compose up -d --scale worker=5' is running natively.")
    
    while True:
        try:
            # Randomly trigger a chaos pattern
            chaos_action = random.choice([inject_sudden_death, inject_network_partition])
            chaos_action()
            verify_system_stability()
            
            # System grace period
            idle_time = random.randint(30, 60)
            logger.info(f"Chaos event concluded. Sleeping for {idle_time}s to measure system stabilization...\n")
            time.sleep(idle_time)
            
        except KeyboardInterrupt:
            logger.info("Chaos Engine gracefully shutting down.")
            sys.exit(0)
