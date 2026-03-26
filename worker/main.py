import asyncio
import httpx
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] Worker: %(message)s")
logger = logging.getLogger(__name__)

MASTER_URL = os.getenv("MASTER_URL", "http://localhost:8000")
CAPACITY = int(os.getenv("WORKER_CAPACITY", "100"))

class WorkerNode:
    def __init__(self):
        self.worker_id = None
        self.client = httpx.AsyncClient(base_url=MASTER_URL, timeout=5.0)
        self.current_load = 0.0

    async def register(self):
        logger.info(f"Attempting to register with master at {MASTER_URL}...")
        try:
            res = await self.client.post("/workers/register", json={"capacity": CAPACITY})
            res.raise_for_status()
            data = res.json()
            self.worker_id = data["id"]
            logger.info(f"Registered successfully as worker {self.worker_id}")
        except Exception as e:
            logger.error(f"Failed to register with master: {e}")
            raise

    async def heartbeat_loop(self):
        while True:
            if not self.worker_id:
                await asyncio.sleep(2)
                continue
                
            try:
                # In a real app, current_load is dynamically derived from CPU/Mem metrics
                payload = {"current_load": self.current_load}
                res = await self.client.post(f"/workers/{self.worker_id}/heartbeat", json=payload)
                res.raise_for_status()
                logger.debug("Heartbeat accepted by master")
            except Exception as e:
                logger.warning(f"Heartbeat to master failed: {e}. Retrying sequentially...")
            
            await asyncio.sleep(2) # Sends heartbeat every 2 seconds

    async def execution_loop(self):
        # Stub loop: Polling master or reading queue for tasks would happen here
        while True:
            await asyncio.sleep(1)

    async def run(self):
        await self.register()
        
        # Concurrently fire and forget background daemons
        await asyncio.gather(
            self.heartbeat_loop(),
            self.execution_loop()
        )

if __name__ == "__main__":
    worker = WorkerNode()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker gracefully shutting down")
