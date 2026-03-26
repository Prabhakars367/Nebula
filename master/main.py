import logging
from fastapi import FastAPI
from master.api.routes_tasks import router as tasks_router
from master.api.routes_workers import router as workers_router
from master.core.config import settings

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from contextlib import asynccontextmanager
import asyncio
from master.services.worker_monitor import detect_failures_and_reassign
from master.services.scheduler import scheduling_daemon
from master.scheduler.optimizer import run_optimizer_loop
from master.core.db import AsyncSessionLocal

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor_task = asyncio.create_task(detect_failures_and_reassign())
    scheduler_task = asyncio.create_task(scheduling_daemon())
    optimizer_task = asyncio.create_task(run_optimizer_loop(AsyncSessionLocal))
    yield
    monitor_task.cancel()
    scheduler_task.cancel()
    optimizer_task.cancel()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Distributed Task Orchestrator Master Node",
    version="1.0.0",
    lifespan=lifespan
)

# Include API Routers
app.include_router(tasks_router)
app.include_router(workers_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
