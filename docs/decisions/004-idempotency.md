# Decision 004: Submission Idempotency

## Status
Accepted

## Date
2026-10-18

## Context
Network timeouts can cause browsers to retry submission requests. Without idempotency, retries create duplicate leads. The platform must support an optional idempotency key to prevent duplicate storage.

## Options Considered

### Option A: Client-Generated Idempotency Key (Header)
- **Pros:** Client controls retry semantics, standard pattern (Stripe-style), works across retries
- **Cons:** Requires client cooperation, key storage on client

### Option B: Server-Generated Fingerprint (Auto-Dedup)
- **Pros:** Transparent to client, no header needed
- **Cons:** False positives (different submissions with same fingerprint), complex fingerprint logic

### Option C: No Idempotency (Accept Duplicates)
- **Pros:** Simplest implementation
- **Cons:** Violates requirement "Idempotency is implemented and proven where it matters"

## Decision
Implement **Client-Generated Idempotency Key via Header** with the following contract:

### Header
- Name: `Idempotency-Key`
- Format: Client-generated UUID v4 (recommended) or any string ≤ 255 chars
- Optional: If absent, no deduplication attempted

### Scope & Storage
- Scope: Per `widget_id` (public widget ID) — keys don't collide across widgets
- Table: `idempotency_records` (see `database_schema.md` §4.6)
- Columns: `id`, `workspace_id`, `widget_id`, `idempotency_key`, `request_fingerprint`, `submission_id`, `created_at`, `expires_at`
- TTL: 24 hours (`expires_at = created_at + 24h`)
- Unique constraint: `(widget_id, idempotency_key)`

### Request Fingerprint
- Algorithm: SHA-256 of canonicalized request body (`data` object only, sorted keys)
- Purpose: Detect key reuse with different payload
- Stored in `request_fingerprint` column

### Behavior
| Scenario | Response |
|----------|----------|
| First request with key | Process normally, store key + fingerprint + submission_id, return `201` |
| Retry with same key + same fingerprint | Return `200` with original submission response (replay) |
| Retry with same key + different fingerprint | Return `409 Conflict` with code `IDEMPOTENCY_CONFLICT` |
| Key expired (TTL) | Treat as new key |
| No key provided | No deduplication, process normally |

### Concurrency Safety
- Use database unique constraint on `(widget_id, idempotency_key)` to prevent race conditions
- Insert idempotency record and submission in same transaction
- On unique violation: fetch existing record, compare fingerprint, return replay or conflict

### Cleanup
- Background job or migration deletes records where `expires_at < now()`
- Or rely on TTL index if using PostgreSQL partitioning (future)

## Consequences
- **Positive:** Standard pattern, testable, prevents duplicates, clear conflict semantics
- **Negative:** Client must generate/store key; adds table and logic
- **Risk:** Key leakage = replay possible; mitigated by 24h TTL and per-widget scope

## Implementation Notes
- Add `Idempotency-Key` header parsing in submission endpoint
- Create `app/services/idempotency.py` with `claim_key()`, `check_key()` functions
- Store fingerprint as hex string (64 chars)
- Return `Idempotency-Key` in response headers for client correlation (optional)
- Test: concurrent requests with same key → only one submission created

## Related Documents
- `docs/architecture.md` §6, §7
- `docs/api_contracts.md` §5.2
- `docs/database_schema.md` §4.6
- `docs/security_spec.md` §9
- `docs/submission_flow.md` §4, Stage 6
- `docs/event_spec.md` §8