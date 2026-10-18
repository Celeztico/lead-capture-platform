# Submission Flow

## 1. Purpose and status

This document describes the complete lifecycle of a lead submission in the **Lead-Capture Platform**, from the visitor's browser request through validation, abuse controls, database persistence, optional enrichment, and notification delivery.

It defines the intended success/failure boundary for the most important product workflow and provides a sequence diagram for implementation and testing.

> **Implementation status:** This is the proposed workflow contract. The actual transaction boundaries, idempotency mechanism, rate-limit store, job runner and notification delivery mode must be verified against the implementation. Do not claim durable retries or exactly-once processing unless the code and tests support those guarantees.

## 2. Workflow goals

The submission workflow must:

- Accept only valid submissions for an enabled widget.
- Validate all input on the server, regardless of client-side checks.
- Apply rate limits and spam prevention before expensive work.
- Preserve tenant ownership and data integrity.
- Persist accepted leads before treating them as captured.
- Attempt optional geolocation and notification work without losing an already-stored lead.
- Handle duplicate requests and retries according to a documented policy.
- Return a stable response that lets the widget distinguish rejection from successful capture.
- Avoid leaking sensitive data through responses, logs or provider errors.

## 3. High-level sequence

```mermaid
sequenceDiagram
    autonumber
    actor Visitor as Website visitor
    participant Widget as JavaScript widget
    participant API as FastAPI public route
    participant Guard as Validation and abuse controls
    participant Service as Submission service
    participant DB as PostgreSQL
    participant GeoA as Geolocation provider A
    participant GeoB as Geolocation provider B
    participant Jobs as Background job runner (if enabled)
    participant Mail as Email provider
    participant Hook as Customer webhook

    Visitor->>Widget: Fill in and submit form
    Widget->>API: POST /public/v1/widgets/{public_widget_id}/submissions
    API->>Guard: Parse request, enforce size and content-type limits
    Guard->>Service: Valid request envelope
    Service->>DB: Resolve widget and owning workspace
    DB-->>Service: Widget, status and public configuration
    Service->>Guard: Validate fields, rate limit and spam checks
    alt Request rejected before persistence
        Guard-->>API: Validation / abuse error
        API-->>Widget: 4xx or 429 error
        Widget-->>Visitor: Show actionable error
    else Request is acceptable
        opt Idempotency is enabled
            Service->>DB: Claim idempotency key / check prior result
            DB-->>Service: New key or prior result
        end
        Service->>DB: Insert submission (and idempotency result if used)
        DB-->>Service: Commit succeeds
        alt Side effects are asynchronous
            Service->>DB: Persist jobs/outbox records, if durable jobs are used
            DB-->>Service: Job records committed
            Service-->>API: Submission stored
            API-->>Widget: 201 accepted
            Jobs->>DB: Claim eligible job
            Jobs->>GeoA: Enrich if configured
            alt Provider A fails or has no usable result
                Jobs->>GeoB: Try fallback provider
            end
            Jobs->>Mail: Send notification if configured
            Jobs->>Hook: Deliver webhook if configured
        else Side effects are synchronous
            Service->>GeoA: Enrich if configured
            alt Provider A fails or has no usable result
                Service->>GeoB: Try fallback provider
            end
            Service->>Mail: Send notification if configured
            Service->>Hook: Deliver webhook if configured
            Service-->>API: Submission stored; side-effect outcomes recorded if supported
            API-->>Widget: 201 accepted
        end
        Widget-->>Visitor: Show success message
    end
```

The diagram shows alternative integration modes. The implementation must choose one. For reliable delivery, persist a submission and durable job/outbox records in the same transaction where feasible. If work is scheduled only in process memory, it can be lost when the process restarts and must not be described as durable.

## 4. Detailed processing stages

### Stage 1 — Receive the request

Endpoint:

```http
POST /public/v1/widgets/{public_widget_id}/submissions
Content-Type: application/json
```

The request contains visitor fields under `data`, as defined by `widget_contract.md`.

At the HTTP boundary:
- Require the supported content type.
- Parse JSON and reject malformed bodies.
- Enforce a request-body size limit before fully processing large payloads.
- Apply an appropriate request timeout.
- Generate or propagate a request/correlation ID for safe diagnostics.
- Do not log the raw form body.

**Reject before persistence** when the body is malformed, the content type is unsupported, or configured size/time limits are exceeded.

### Stage 2 — Resolve widget and ownership

1. Look up the widget using `public_widget_id`.
2. Confirm that it exists and is publicly available.
3. Confirm that its lifecycle state is `active`.
4. Resolve the owning workspace from trusted database data.
5. Load the configuration needed to validate the submitted fields.

Do not accept a visitor-provided `workspace_id` or internal `widget_id` as authoritative.

**Reject before persistence** when the widget does not exist, is disabled/archived, or is not eligible to receive submissions. Return a non-sensitive response that does not reveal private workspace details.

### Stage 3 — Origin and cross-origin policy

Browsers may send an `Origin` header. If the product implements a per-widget allowed-origin policy, compare the supplied origin against that policy using a documented normalization rule.

Important distinctions:
- CORS controls whether a browser permits frontend JavaScript to read a response; it is not authentication.
- Non-browser clients can call the public endpoint directly and can forge headers.
- The origin policy must not be the only spam or authorization control.
- Define behavior for absent or opaque origins instead of assuming they are valid.

**Reject before persistence** if the implementation's explicit origin policy rejects the request. If origin checking is not part of the implemented product, do not claim that it is enforced.

### Stage 4 — Validate and normalize submitted fields

Validate the request against the widget's current supported configuration.

Checks include:
- `data` is an object with the expected shape.
- Field names are supported by the widget.
- Required fields are present and non-empty after normalization.
- Values have the expected type.
- Text lengths, field count and total payload size are within configured limits.
- Email fields pass basic syntax validation where applicable.
- Unknown fields follow one consistent policy: reject them or ignore them explicitly. Rejecting unknown fields is the safer default for a strict contract.
- Server-controlled values such as IDs, timestamps, workspace ownership and delivery status cannot be set by the visitor.

Normalize only where the field semantics make it safe, such as trimming surrounding whitespace. Do not unexpectedly rewrite meaningful user input.

**Reject before persistence** when the request violates the field schema or business rules. Return a stable validation error with safe field-level details when possible.

### Stage 5 — Rate limiting and spam prevention

Apply abuse controls before provider calls and before expensive persistence work.

Possible controls:
- Rate limit by client IP, widget ID, or a combination.
- Validate IP addresses only from the direct connection or explicitly trusted proxy headers.
- Use a honeypot or other low-friction spam signal if implemented.
- Enforce payload and field-size limits.
- Detect obviously malformed or repeated abuse patterns.
- Keep spam checks bounded in time and resource consumption.

Do not assume a browser-supplied IP header is trustworthy. Configure reverse-proxy trust explicitly.

**Reject before persistence** when a hard rate limit is exceeded or a configured spam rule marks the request as disallowed. Return `429 Too Many Requests` for rate limiting, with `Retry-After` when available. Use a documented response for spam rejection; do not reveal detailed anti-abuse rules that make bypass easier.

The rate-limit key, thresholds, storage backend and behavior during limiter failure must be selected and tested. If the limiter is unavailable, choose an explicit fail-open or fail-closed policy according to the abuse risk; do not leave this behavior accidental.

### Stage 6 — Idempotency and duplicate handling

Idempotency is recommended because a browser may retry after a timeout even when the first request was stored.

If supported:
1. Read the idempotency key from the documented request header.
2. Scope the key, for example to the widget, so unrelated widgets do not collide.
3. Compute a server-side request fingerprint.
4. Atomically claim the key and associate it with the accepted result.
5. If the same key and same fingerprint already succeeded, return the documented replay result without creating another submission.
6. If the same key is reused with a different fingerprint, return `409 Conflict`.
7. Ensure concurrent requests using the same key cannot create multiple submissions.

The idempotency record and submission result should be committed atomically where possible. A pre-check without a database uniqueness constraint is not sufficient under concurrency.

If idempotency is not implemented, document that duplicate submissions are possible after ambiguous network failures. Do not claim exactly-once processing.

### Stage 7 — Persist the submission

The database is the source of truth for captured leads.

Within a clear transaction:
1. Insert the submission with server-generated ID and timestamp.
2. Associate it with the resolved widget and owning workspace.
3. Store only validated fields.
4. If idempotency is enabled, persist the key/result relationship atomically.
5. If durable asynchronous work is enabled, insert job/outbox records in the same transaction when feasible.
6. Commit the transaction.

A submission is **captured only after the transaction commits successfully**.

**Reject/fail without claiming success** when PostgreSQL is unavailable, a required constraint fails, or the transaction cannot commit. Return an appropriate server error and log a redacted diagnostic with the request ID. Do not tell the visitor the submission succeeded if no durable record was created.

Avoid holding a database transaction open while waiting for geolocation, email or webhook providers.

### Stage 8 — Geolocation enrichment and fallback

Geolocation is optional enrichment; it is not required to capture a lead.

Proposed provider policy:
1. Use provider A when enrichment is enabled and the required input is available.
2. Apply a short timeout and validate the response.
3. If provider A fails, times out, returns an unusable response, or has no usable result, attempt provider B.
4. If provider B also fails, record or log a sanitized enrichment failure if supported and continue without enrichment.

Send only the data needed for enrichment and account for privacy/retention requirements.

**Allow the submission to succeed** if either provider fails or both providers fail after the submission has been stored. Enrichment failure must not delete or invalidate the submission.

The exact input used for geolocation, provider names, timeout values and fallback conditions must be finalized in implementation configuration and tests.

### Stage 9 — Email and webhook side effects

Notifications are side effects, not the source of truth for whether a lead was captured.

For each enabled side effect:
- Build a minimal, documented payload.
- Apply explicit connection and response timeouts.
- Validate provider responses.
- Record delivery state or a sanitized error if supported.
- Retry only under a bounded, documented policy.
- Make repeated delivery safe where possible.
- Avoid logging full lead data or secret headers.

For customer-configured webhook destinations, enforce destination validation and protections against server-side request forgery (SSRF), including unsafe internal or metadata-service addresses. Do not allow arbitrary webhook URLs until this control exists.

**Allow the submission to succeed** if email or webhook delivery fails after the lead is stored. Report the delivery failure through job/delivery state, logs or metrics rather than changing the stored lead into a rejected submission.

### Stage 10 — Return the final HTTP response

The public API returns success only after the submission is durably stored.

For a newly stored lead, the proposed response is:

```http
HTTP/1.1 201 Created
Content-Type: application/json
```

```json
{
  "id": "0e1b1a0b-c4c4-4d66-9b5e-4f3a04c65e16",
  "status": "accepted",
  "message": "Your submission has been received."
}
```

The widget then displays the configured success message.

For asynchronous side effects, the API can respond after the submission and durable job/outbox records commit. For synchronous side effects, it can respond after those attempts finish, but their failures must not override a successful persistence outcome. The chosen behavior must be consistent and tested.

If the server commits the submission but the response is lost, the visitor may see a network error despite successful capture. Idempotency is the recommended way to make safe retries possible.

## 5. Failure policy matrix

| Failure or condition | Persist submission? | Expected result |
|---|---:|---|
| Malformed JSON | No | Reject with client error |
| Unsupported content type | No | Reject with `415` |
| Request body too large | No | Reject with `413` |
| Unknown public widget | No | Reject with `404` |
| Widget disabled or archived | No | Reject with documented unavailable response |
| Origin rejected by configured policy | No | Reject according to policy |
| Required field missing or invalid | No | Reject with validation error |
| Unknown field under strict validation | No | Reject with validation error |
| Rate limit exceeded | No | Reject with `429` |
| Spam rule rejects request | No | Reject with documented anti-abuse response |
| Idempotency key reused with different payload | No new row | Return `409` if idempotency is implemented |
| Same successful key and same payload retried | No duplicate row | Replay documented successful result |
| PostgreSQL unavailable before commit | No confirmed capture | Return server/dependency error; do not claim success |
| Database constraint or commit failure | No confirmed capture | Return server error; record safe diagnostics |
| Geolocation provider A fails | Yes, if persistence committed | Try provider B; capture remains successful |
| Geolocation provider B also fails | Yes, if persistence committed | Continue without enrichment |
| Email delivery fails after commit | Yes | Capture succeeds; record/retry delivery failure if supported |
| Webhook delivery fails after commit | Yes | Capture succeeds; record/retry delivery failure if supported |
| Background worker fails after commit | Yes | Capture remains; retry or mark job failed according to policy |
| Browser times out after server commit | Possibly yes | Outcome is uncertain to client; retry safely with idempotency if available |
| Optional analytics/metrics backend fails | Yes | Capture succeeds; telemetry failure must not block it |

The key boundary is **before versus after the database commit**. Failures before commit can prevent capture. Failures in optional work after commit must not retroactively reject the captured lead.

## 6. Transactions, retries and idempotency guarantees

### 6.1 Transaction boundary

The minimum atomic operation is insertion of the submission record. If idempotency is supported, the submission and its idempotency result should be committed atomically. If durable background work is required, insert the relevant job/outbox records in that same transaction where feasible.

Do not make an external network request inside a database transaction unless there is a compelling, documented reason.

### 6.2 Retry policy

- Retry transient provider failures only within a bounded attempt count and time window.
- Use exponential backoff with jitter for background retries where appropriate.
- Do not retry permanent validation errors.
- Treat `429` and provider retry guidance according to the documented policy.
- Make side effects idempotent or track delivery attempts to reduce duplicate notifications.
- Record terminal failures in a way that can be diagnosed and, if safe, replayed.
- Never claim exactly-once delivery; practical integrations usually provide at-least-once attempts or best-effort behavior.

### 6.3 Durable versus in-process background work

A framework's in-process background task can be useful for a small demonstration but may be lost on process restart. If the capstone requires reliable retryable work, use a durable queue, persisted job table or transactional outbox and a worker that claims jobs safely.

Document which mechanism is actually implemented. The existence of a `background_jobs` table alone does not provide reliable processing without a worker and retry/recovery logic.

## 7. Logging and observability

Capture enough operational context to diagnose failures without collecting unnecessary lead data.

Useful fields:
- Request/correlation ID
- Public widget identifier or a safe internal reference
- Processing stage and outcome
- HTTP status and latency
- Rate-limit decision category
- Persistence success/failure
- Provider name, attempt number and sanitized error category
- Job or delivery ID, if available

Do not log:
- Raw submission bodies
- Passwords, tokens or secret headers
- Full provider responses that may contain personal data
- Unnecessary IP/location details
- Webhook secrets or sensitive destination credentials

Track counts and latency for accepted submissions, validation rejections, rate limits, database failures, geolocation fallback, notification failures and job retries when telemetry is available.

## 8. Test scenarios

At minimum, integration tests should cover:

1. Valid submission is stored and returns the documented success response.
2. Unknown, disabled and archived widgets are rejected.
3. Required, unknown, oversized and invalid fields are handled correctly.
4. Rejected origins behave according to the configured policy.
5. Rate limiting returns `429` and normal requests still succeed below the threshold.
6. Spam checks reject a known test pattern without storing a lead.
7. Duplicate idempotency requests create at most one submission, including concurrent requests, if supported.
8. Reusing a key with a different payload returns the documented conflict response.
9. Database failure does not return a false success response.
10. Provider A failure triggers provider B.
11. Failure of both geolocation providers does not lose a stored submission.
12. Email and webhook failures do not change a persisted submission into a rejected lead.
13. Background retries are bounded and terminal failure is visible, if jobs are implemented.
14. A timeout after commit can be retried safely if idempotency is supported.
15. Cross-workspace users cannot read or alter the resulting submission.
16. Error responses and logs do not expose secrets or raw lead contents.

Use deterministic mocks/fakes for provider failures rather than depending on real third-party outages during tests.

## 9. Related documentation

- [`architecture.md`](architecture.md) — system components and trust boundaries
- [`domain_models.md`](domain_models.md) — submission and widget lifecycle rules
- [`database_schema.md`](database_schema.md) — persistence and idempotency/job tables
- [`api_contracts.md`](api_contracts.md) — endpoint paths, response schemas and status codes
- [`widget_contract.md`](widget_contract.md) — browser request/response behavior
- [`security_spec.md`](security_spec.md) — rate limiting, spam prevention and security controls
- [`event_spec.md`](event_spec.md) — asynchronous event and job contracts, if implemented

---

## Maintenance rule

Keep this flow aligned with the actual service code, transaction boundaries, job mechanism and tests. Update the sequence diagram and failure matrix whenever processing order or failure semantics change. Label planned capabilities clearly until they are implemented and verified.
