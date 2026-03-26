-- ENUM Definitions
CREATE TYPE worker_status AS ENUM ('ACTIVE', 'DEAD', 'DRAINING');
CREATE TYPE task_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED');

-- Workers Table (Tracks the ephemeral computing nodes)
CREATE TABLE workers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status worker_status NOT NULL DEFAULT 'ACTIVE',
    capacity INT NOT NULL DEFAULT 100,
    current_load INT NOT NULL DEFAULT 0,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tasks Table (Core state machine)
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status task_status NOT NULL DEFAULT 'PENDING',
    payload JSONB NOT NULL,                 -- Input task data
    resource_reqs JSONB DEFAULT '{}',       -- CPU/RAM requirements
    retries INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    worker_id UUID REFERENCES workers(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,                 -- When it actually began RUNNING
    completed_at TIMESTAMPTZ,               -- When it finished
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Task Execution Logs Table (Audit trail of retries & failures)
CREATE TABLE task_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    worker_id UUID REFERENCES workers(id) ON DELETE SET NULL,
    attempt_number INT NOT NULL,
    error_message TEXT,                     
    stack_trace TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Worker Metrics Table (Telemetry History for Predictor Algorithm)
CREATE TABLE worker_metrics (
    id BIGSERIAL PRIMARY KEY,
    worker_id UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    cpu_usage NUMERIC(5, 2) NOT NULL,       
    ram_usage BIGINT NOT NULL,              
    active_tasks INT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-------------------------------------------------------------------------------
-- INDEXES FOR HIGH-THROUGHPUT (<200ms latency at 10K+ concurrency)
-------------------------------------------------------------------------------

-- 1. Scheduler Queue Polling (Lightning fast PENDING retrieval)
CREATE INDEX idx_tasks_status_created_at ON tasks(status, created_at) 
WHERE status = 'PENDING';

-- 2. Finding dead workers efficiently (Scans status + heartbeat combo)
CREATE INDEX idx_workers_status_heartbeat ON workers(status, last_heartbeat);

-- 3. Fast lookup for tasks currently held by a specific worker (Failure recovery)
CREATE INDEX idx_tasks_worker_id_status ON tasks(worker_id, status) 
WHERE status = 'RUNNING';

-- 4. Fast Task Logs lookups 
CREATE INDEX idx_task_logs_task_id ON task_logs(task_id);

-- 5. Time-series telemetry bounds optimization
CREATE INDEX idx_worker_metrics_recorded_at ON worker_metrics(recorded_at DESC);
CREATE INDEX idx_worker_metrics_worker_id_recorded_at ON worker_metrics(worker_id, recorded_at DESC);

-------------------------------------------------------------------------------
-- SAMPLE QUERIES
-------------------------------------------------------------------------------

-- A. Detecting Dead Workers (Run by Master background task every few seconds)
/*
UPDATE workers
SET status = 'DEAD'
WHERE status = 'ACTIVE' 
  AND last_heartbeat < NOW() - INTERVAL '10 seconds'
RETURNING id;
*/

-- B. Reassigning Tasks (Run immediately after detecting dead workers)
/*
-- Step 1: Set out-of-retries tasks to FAILED
UPDATE tasks 
SET status = 'FAILED', 
    updated_at = NOW(),
    completed_at = NOW()
WHERE worker_id = ANY(ARRAY['<dead_worker_uuid>']::UUID[])
  AND status = 'RUNNING'
  AND retries >= max_retries;

-- Step 2: Requeue tasks that have remaining retries
UPDATE tasks 
SET status = 'PENDING',
    retries = retries + 1,
    worker_id = NULL,
    started_at = NULL,
    updated_at = NOW()
WHERE worker_id = ANY(ARRAY['<dead_worker_uuid>']::UUID[])
  AND status = 'RUNNING'
  AND retries < max_retries;
*/
