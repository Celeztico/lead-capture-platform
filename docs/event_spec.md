# Event and Background Job Specification

**Status:** Proposed contract  
**Scope:** Lead-Capture Platform  
**Audience:** Backend implementation, testing, and operations

> This document defines the intended contract for asynchronous work. It is a design baseline, not proof that a queue, worker, retry mechanism, or alerting integration has already been implemented. Update it alongside the actual job models, producers, consumers, and deployment configuration.

## 1. Purpose

The platform must capture a valid lead without making the public submission request depend on slower or less reliable integrations. After the submission is durably stored, optional work—such as geolocation enrichment, email notifications, and webhook delivery—can run asynchronously.

The central invariant is:

**A failure in optional asynchronous work must not undo or misrepresent a lead submission that has already committed to the database.**

Asynchronous processing should be introduced only where it improves request reliability or moves slow work out of the HTTP response path. Keep the first implementation small and explicit.

## 2. Terminology

- **Job:** A unit of work that a worker can attempt and retry.
- **Producer:** Code that creates or schedules a job.
- **Consumer/worker:** Code that claims a job, executes it, and records its outcome.
- **Attempt:** One execution of a job, including a retry.
- **Terminal failure:** A job has exhausted its retry policy or failed permanently and will not be retried automatically.
- **Dead-letter state:** A stored terminal-failure state used for inspection and recovery. A separate message broker dead-letter queue is not required by this specification.
- **Idempotent handler:** A handler that can receive the same job more than once without creating duplicate externally visible effects.

## 3. Initial job types

Start with a small set of job types. These names are proposed identifiers and should be treated as stable once they are persisted in the database or emitted to a broker.

| Job type | Purpose | Producer | Consumer |
|---|---|---|---|
| `submission.geolocate` | Enrich a stored submission with location data using provider A, then provider B if needed | Submission service, after the submission is committed | Geolocation worker |
| `submission.send_notification` | Send a notification for a newly captured lead, if the workspace/widget configuration enables it | Submission service, after the submission is committed | Notification worker |
| `submission.deliver_webhook` | Deliver a lead event to a configured webhook destination, if enabled | Submission service, after the submission is committed | Webhook worker |

These jobs are optional integrations around the core database write. If a feature is not enabled or configured, do not create its job. Do not create a job for a submission that failed validation or did not commit.

### 3.1 Event versus job

The initial design may use persisted jobs directly rather than introducing a separate event bus. For example, the submission service can create a `submission.geolocate` job referencing a stored submission. A future event such as `submission.created` may be introduced if multiple consumers need a shared domain-event contract.

Avoid maintaining both a separate event record and equivalent jobs unless there is a clear need for that additional complexity.

## 4. Common job envelope

Every persisted job should use a common envelope, whether stored in a PostgreSQL-backed job table or represented by a queue message.

```json
{
  "job_id": "job_01J...",
  "job_type": "submission.geolocate",
  "schema_version": 1,
  "workspace_id": "ws_01J...",
  "submission_id": "sub_01J...",
  "created_at": "2026-08-27T12:00:00Z",
  "attempt": 0,
  "correlation_id": "req_01J...",
  "payload": {}
}
```

Field meanings:

- `job_id`: Unique identifier for this job instance.
- `job_type`: Stable, namespaced job type.
- `schema_version`: Version of the payload contract.
- `workspace_id`: Tenant scope used for authorization and consistency checks.
- `submission_id`: The stored submission this job relates to.
- `created_at`: UTC creation timestamp.
- `attempt`: Number of attempts already started or completed, according to the implementation's documented convention. Use one convention consistently.
- `correlation_id`: Request or trace identifier used to connect the submission request to downstream work. It must not contain secrets.
- `payload`: Small job-specific data. Prefer identifiers and read current canonical data from the database instead of copying unnecessary lead PII into a queue.

Do not use a public widget ID, email address, or arbitrary user-controlled string as the sole job identifier. Validate all identifiers and confirm that referenced records belong to the specified workspace before processing.

## 5. Job payload contracts

### 5.1 `submission.geolocate`

Purpose: Enrich an already stored submission with approximate location data.

```json
{
  "submission_id": "sub_01J...",
  "provider_policy": "provider_a_then_b"
}
```

Processing contract:

1. Load the submission and verify its workspace association.
2. Determine whether the data needed for geolocation is present and permitted for processing.
3. Call provider A.
4. If provider A fails or returns no usable result, try provider B according to the configured fallback policy.
5. Store a successful result only if it is still applicable to the submission.
6. If both providers fail, record a safe, structured failure outcome and leave the original submission intact.

Do not log full IP addresses or raw provider responses by default. If the product supports IP-based geolocation, document retention and privacy rules separately and avoid collecting more precise data than required.

### 5.2 `submission.send_notification`

Purpose: Send an email or other configured notification about a stored lead.

```json
{
  "submission_id": "sub_01J...",
  "notification_kind": "new_lead"
}
```

Processing contract:

1. Load the submission and the applicable workspace/widget notification settings.
2. Verify that notification delivery is enabled and that the destination is valid.
3. Send using the configured provider.
4. Record the provider outcome and safe diagnostic metadata.
5. Retry transient failures; do not retry known permanent configuration or validation errors indefinitely.

Do not include unnecessary lead fields in the job payload. Resolve recipients and message templates from trusted configuration where practical.

### 5.3 `submission.deliver_webhook`

Purpose: Deliver a stored lead to a configured external webhook endpoint.

```json
{
  "submission_id": "sub_01J...",
  "webhook_config_id": "whc_01J...",
  "delivery_event": "submission.created"
}
```

Processing contract:

1. Load the submission and webhook configuration; verify they belong to the same workspace.
2. Revalidate that the configuration is enabled and the destination remains permitted.
3. Send a versioned event envelope and a stable delivery identifier.
4. Treat timeouts and eligible server errors as retryable; classify permanent destination/configuration failures explicitly.
5. Record each delivery attempt and the final outcome.

Webhook URLs are security-sensitive. Prevent SSRF by rejecting loopback, link-local, private, and otherwise prohibited destinations as appropriate; validate resolved addresses and re-check redirects. Do not forward credentials or internal headers to customer-controlled destinations.

Suggested webhook body:

```json
{
  "event_id": "evt_01J...",
  "event_type": "submission.created",
  "schema_version": 1,
  "created_at": "2026-08-27T12:00:00Z",
  "workspace_id": "ws_01J...",
  "data": {
    "submission_id": "sub_01J..."
  }
}
```

Include only the fields required by the webhook contract. If consumers need more submission data, explicitly define and version those fields rather than silently expanding the payload.

## 6. Producer and persistence rules

1. Validate the public submission request.
2. Apply origin, rate-limit, spam, and idempotency checks.
3. Store the submission in PostgreSQL.
4. Persist the required asynchronous job records in a way that cannot leave a committed submission without its intended jobs.
5. Commit the submission and its jobs atomically where the implementation uses a database-backed queue/outbox.
6. Return the submission success response after the durable write is complete; do not wait for geolocation, email, or webhook network calls.

**Recommended implementation:** use a transactional database-backed job table or transactional outbox for the first version. A job must not be published before the submission transaction commits, and a process crash must not silently lose work between the database commit and job publication.

If the project initially schedules in-process background tasks, document that this is best-effort and not durable across process restarts. It should not be described as providing guaranteed delivery. The durable job/outbox approach is preferred for production-like behavior.

## 7. Retry policy

Use bounded retries with exponential backoff and jitter for transient failures. The exact limits should be configurable and documented in the worker implementation.

Suggested starting policy:

| Setting | Proposed default |
|---|---|
| Maximum attempts | 5 total attempts, including the first attempt |
| Backoff | Exponential: 5 s, 15 s, 45 s, 2 min, then stop |
| Jitter | Add a small random delay to spread simultaneous retries |
| Retryable failures | Network timeouts, connection errors, HTTP 429, and eligible HTTP 5xx responses |
| Usually permanent failures | Invalid payload/schema, deleted or inaccessible referenced record, invalid destination, unsupported event version, and non-retryable HTTP 4xx |
| Provider fallback | For geolocation, try provider B after provider A fails or returns no usable result; then retry the job later only if the overall operation is classified as transient |

The delay sequence is illustrative; implement a single consistent policy and avoid retrying both in a tight inner loop and again at the job level without a documented limit. Honor `Retry-After` where appropriate, subject to a maximum delay.

Classify errors by job type. For example, a webhook HTTP 429 is normally retryable, while a webhook HTTP 404 may be a configuration/destination failure. Never retry malformed payloads endlessly.

## 8. Idempotency and duplicate delivery

Assume jobs may be delivered more than once. A worker can crash after an external provider accepts a request but before the worker records success.

Required behavior:

- Every job has a stable `job_id`.
- Every webhook delivery has a stable `event_id` or delivery ID reused across retries.
- Handlers check whether the relevant operation has already completed before repeating database-side effects.
- Database writes use appropriate uniqueness constraints or conditional updates to prevent duplicate enrichment records or duplicate job completion records.
- Notifications and webhooks should pass the stable idempotency/delivery key to providers or receivers when supported.
- If the external service does not support idempotency, document that exactly-once external delivery cannot be guaranteed; duplicate delivery remains possible.

For webhook receivers, document that consumers should deduplicate by `event_id`. For email, a stable internal notification ID can prevent the application from intentionally enqueueing the same logical notification twice, but it cannot guarantee that an external email provider will never deliver duplicates.

## 9. Ordering and concurrency

No global ordering guarantee is provided.

- Jobs for different submissions may run concurrently.
- Retries may cause a later-created job to finish before an earlier one.
- If multiple job types exist for one submission, their completion order is not guaranteed.
- A consumer must not assume geolocation completes before notification or webhook delivery unless an explicit dependency is implemented.
- Use atomic job claiming or a lease/visibility timeout to prevent ordinary concurrent workers from processing the same job simultaneously.
- If a future feature requires ordering for a specific aggregate, define the ordering key, locking strategy, and failure behavior before implementing it.

Prefer independent, idempotent jobs over a long chain of dependent tasks.

## 10. Job state and storage

If jobs are stored in PostgreSQL, use a small explicit state machine. Suggested states:

- `pending`: Ready for processing.
- `running`: Claimed by a worker and not yet completed.
- `retry_wait`: Failed transiently and scheduled for a later attempt.
- `succeeded`: Completed successfully.
- `dead_letter`: Permanently failed or exhausted the retry budget.
- `cancelled`: Cancelled because the work is no longer applicable or was explicitly stopped.

Suggested fields:

| Field | Purpose |
|---|---|
| `id` | Stable primary key/job ID |
| `job_type`, `schema_version` | Handler and payload contract |
| `workspace_id`, `submission_id` | Tenant and domain references |
| `payload` | Small JSON payload |
| `status` | Current state |
| `attempt_count`, `max_attempts` | Retry accounting |
| `available_at` | Earliest time the job may be claimed |
| `locked_at`, `locked_by` | Lease/worker claim metadata |
| `last_error_code` | Safe, normalized error classification |
| `last_error_at` | Time of latest failure |
| `created_at`, `updated_at`, `completed_at` | Lifecycle timestamps |
| `correlation_id` | Trace/request correlation |

Do not store secrets in job payloads. Avoid copying full lead data or raw exception messages into the job table. Keep stack traces and provider response bodies out of ordinary user-facing APIs; if retained for diagnostics, apply access controls and redaction.

## 11. Consumer/worker behavior

A worker should:

1. Claim a due job atomically, using a transaction/locking strategy that supports concurrent workers.
2. Confirm the job type and schema version are supported.
3. Validate the payload and referenced records.
4. Execute the handler with explicit timeouts for external calls.
5. Commit handler results and job status safely.
6. On transient failure, increment the attempt count and schedule the next attempt.
7. On permanent failure or exhausted retries, transition to `dead_letter`.
8. Emit structured logs and metrics with `job_id`, `job_type`, `attempt`, and `correlation_id`, avoiding sensitive payload values.

Workers must use bounded network timeouts and should not hold database transactions open while waiting on external HTTP requests. Use a lease timeout or recovery process to return jobs stuck in `running` to a retryable state after a worker crash.

## 12. Terminal failure, visibility, and recovery

Terminal failure must be visible; it must not silently disappear.

Minimum behavior:

- Mark the job `dead_letter` with a normalized error code and timestamps.
- Emit a structured error log and increment a failure metric.
- Alert when terminal failures exceed a configured threshold or when the oldest pending job exceeds an operational age threshold.
- Provide an operator-only way to inspect safe job metadata and retry a job after the underlying issue is corrected.
- Manual replay must preserve the original job/event identity when replaying the same logical delivery, or create a new explicit replay identity with an audit trail. Document which approach is used.
- Replaying a job must still pass idempotency checks and current security validation.
- Do not expose internal stack traces, provider secrets, full payload PII, or administrative retry controls through public endpoints.

A recovery procedure should identify the failure reason, correct configuration or provider issues, decide whether replay is safe, then requeue with a recorded operator/action reason. Do not automatically replay permanent failures without fixing their cause.

## 13. Monitoring and operational signals

Track at least:

- Number of jobs by type and state.
- Attempts and retry counts by job type.
- Job processing duration and success/failure rate.
- Count of terminal failures.
- Age of the oldest pending/retry-wait job.
- Worker heartbeat/availability.
- External provider latency and error rates, with sensitive data excluded.

Use the correlation ID to trace the original submission request and its asynchronous work across logs. Alerting should be actionable and rate-limited to avoid notification floods.

## 14. Security and privacy

- Treat job payloads as untrusted input even when produced internally.
- Enforce tenant association when loading submissions and webhook configurations.
- Keep credentials in environment-based secret configuration or a secret manager, never in payloads or source control.
- Restrict job inspection and replay operations to authorized operators.
- Redact email addresses, IP addresses, lead contents, tokens, and webhook secrets from logs.
- Apply outbound request protections to webhook delivery and provider calls.
- Define retention for completed and terminal jobs so stored payloads and diagnostic metadata do not accumulate indefinitely.
- Do not use the public widget ID as proof of authorization.

## 15. Testing requirements

Tests should cover:

- A valid submission is committed even when every optional job later fails.
- No asynchronous jobs are created for rejected submissions.
- Submission and job/outbox records commit atomically when using the database-backed design.
- Provider A failure triggers provider B for geolocation.
- Transient errors schedule retries with the expected attempt limit and backoff.
- Permanent failures transition to `dead_letter` without repeated retries.
- Duplicate delivery does not duplicate database-side effects.
- Webhook delivery reuses the same event/delivery ID across retries.
- A worker crash or expired lease makes a stuck job recoverable.
- Unsupported schema versions fail visibly and safely.
- Tenant mismatches cannot access or process another workspace's data.
- Logs and error records redact sensitive values.
- A terminal failure is visible through logs/metrics and can be safely replayed by an authorized operator.

## 16. Implementation boundaries and decisions to confirm

Before treating this contract as implemented, record the choices made in code:

- Queue mechanism: PostgreSQL job table/outbox, or external broker.
- Worker execution model and deployment process.
- Actual job type names and payload schemas.
- Attempt-count convention and retry/backoff settings.
- How expired worker leases are recovered.
- Alerting destination and thresholds.
- Operator inspection/replay mechanism.
- Data retention and payload redaction rules.

Keep the initial implementation aligned with the internship scope: durable submission storage first, then reliable asynchronous processing with bounded retries and visible terminal failures. Avoid adding a separate event bus, workflow engine, or distributed tracing stack unless the requirements justify it.

---

## 17. Change management

- Increment `schema_version` when a payload change is not backward-compatible.
- Deploy consumers that understand a new version before producers emit it, where the deployment model permits.
- Keep old handlers available until queued jobs using the old version are drained or safely migrated.
- Treat job type names as stable identifiers once jobs have been persisted.
- Update this document and tests whenever a job's semantics, retry policy, or payload changes.
