# Decision 005: Background Jobs — Persistent Outbox Pattern

## Status
Accepted

## Date
2026-10-18

## Context
The platform must perform optional asynchronous work (geolocation enrichment, email notifications, webhook delivery) after a submission is stored. The shared requirement mandates "at least one background job for slow/bulk work, with retries and a failure alert." The implementation must be durable across process restarts — in-memory fire-and-forget is not acceptable.

## Options Considered

### Option A: PostgreSQL Outbox Table + Poller Worker
- **Pros:** Durable (survives restarts), transactional (same DB as submissions), simple, no external deps, meets "background job with retry" requirement
- **Cons:** Polling latency (seconds), worker must be deployed separately

### Option B: Redis + RQ/Celery
- **Pros:** Mature, supports priorities, scaling
- **Cons:** Extra infrastructure (Redis), extra dependency, more complex for MVP

### Option C: In-Process BackgroundTasks (FastAPI/Starlette)
- **Pros:** Zero infrastructure, simple
- **Cons:** **Not durable** — lost on process restart, cannot claim "durable delivery"

### Option D: External Queue (RabbitMQ, Kafka, SQS)
- **Pros:** Production-grade, durable
- **Cons:** Overkill for MVP, extra infrastructure

## Decision
Use **PostgreSQL Outbox Table + Poller Worker** with the following design:

### Outbox Table: `outbox_events`
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `workspace_id` | UUID | Tenant scope |
| `submission_id` | UUID | FK to submissions |
| `event_type` | VARCHAR(80) | e.g., `submission.geolocate`, `submission.send_notification`, `submission.deliver_webhook` |
| `payload` | JSONB | Minimal args (submission_id, etc.) |
| `status` | VARCHAR(20) | `pending`, `running`, `retrying`, `succeeded`, `dead_letter` |
| `attempt_count` | INTEGER | Default 0 |
| `max_attempts` | INTEGER | Default 5 |
| `available_at` | TIMESTAMPTZ | Earliest execution time (for backoff) |
| `locked_at` | TIMESTAMPTZ | Worker claim timestamp |
| `locked_by` | VARCHAR(100) | Worker identifier |
| `last_error_code` | VARCHAR(80) | Sanitized error category |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### Transactional Guarantee
- Submission INSERT + outbox event INSERTs in **same DB transaction**
- Worker polls `outbox_events` where `status = 'pending' AND available_at <= now()`
- Worker claims job atomically: `UPDATE ... SET status='running', locked_at=now(), locked_by=... WHERE id=... AND status='pending'`

### Job Types (Initial)
1. `submission.geolocate` — Enrich with geo (provider A → B fallback)
2. `submission.send_notification` — Email notification (stub for MVP)
3. `submission.deliver_webhook` — Webhook delivery (stub for MVP)

### Retry Policy
- Max attempts: 5 (configurable)
- Backoff: Exponential with jitter — 5s, 15s, 45s, 2min, 5min
- `available_at = now() + backoff(attempt_count)`
- On transient failure: increment `attempt_count`, set `status='retrying'`, update `available_at`
- On permanent failure or exhausted retries: set `status='dead_letter'`, log alert

### Worker Implementation
- Script: `scripts/worker.py` — runs as separate process
- Poll interval: 5 seconds
- Claims batch of jobs (e.g., 10) per loop
- Processes sequentially per worker
- Structured logs with `job_id`, `event_type`, `attempt`, `correlation_id`
- Graceful shutdown: finish current job, release locks

### Failure Alert
- Log `ERROR` level when job → `dead_letter`
- Include: `job_id`, `event_type`, `submission_id`, `attempt_count`, `last_error_code`
- Future: integrate with alerting (Prometheus Alertmanager, PagerDuty, etc.)

## Consequences
- **Positive:** Durable, transactional, no extra infrastructure, testable, meets requirement
- **Negative:** Polling latency (~5s), worker must be running, no priority queue
- **Mitigation:** Acceptable for MVP; Redis/queue can replace in Phase 11

## Implementation Notes
- Create migration for `outbox_events` table
- Add `app/services/outbox.py` with `enqueue_event()`, `claim_jobs()`, `complete_job()`, `fail_job()`
- Worker: `scripts/worker.py` with main loop, signal handling
- Docker Compose: add `worker` service (depends on `db`, same image, different command)
- Tests: inject fake time, verify retry/backoff, verify dead_letter transition

## Related Documents
- `docs/architecture.md` §4.4, §7
- `docs/database_schema.md` §4.7
- `docs/event_spec.md` §3, §6, §7, §11
- `docs/submission_flow.md` §4, Stage 9-10
- `docs/security_spec.md` §14