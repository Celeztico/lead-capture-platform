# API Contracts

## 1. Purpose and status

This document defines the proposed HTTP contract for the **Lead-Capture Platform**. It describes the endpoints used by authenticated workspace clients, public embeddable widgets, and health probes.

> **Contract status:** This is the initial API design baseline, not a claim that every endpoint is already implemented. Once FastAPI routes and Pydantic schemas exist, verify this document against the generated OpenAPI schema and integration tests. Keep the published contract synchronized with the actual behavior.

## 2. API conventions

### 2.1 Base path and versioning

- Management API base path: `/api/v1`
- Public widget API base path: `/public/v1`
- Widget JavaScript asset path: `/widget/v1`
- Health endpoints: `/health/live` and `/health/ready`
- Use HTTPS outside local development.
- Version the public contract through the URL path. Make breaking changes in a new API version rather than silently changing existing request or response shapes.

Example base URL used in this document:

```text
https://api.example.com
```

Replace this illustrative hostname with the configured deployment URL. Do not hard-code it in application code or widget assets.

### 2.2 Content types and encoding

- JSON request bodies use `Content-Type: application/json`.
- JSON responses use `Content-Type: application/json`.
- The widget JavaScript asset is served with a JavaScript-compatible content type.
- Use UTF-8 encoding.
- Reject unsupported content types on endpoints that require JSON.
- Apply request-body and field-size limits, especially on public submission endpoints.

### 2.3 Identifiers and timestamps

- Use the identifier format selected by the implementation; UUIDs are the proposed default.
- `widget_id` is the internal management identifier.
- `public_widget_id` is used by the embed snippet and public endpoints. It is not an authorization credential.
- Return timestamps as ISO 8601 strings with an explicit timezone, preferably UTC, for example `2026-10-18T12:30:00Z`.
- IDs and timestamps are server-generated unless a contract explicitly says otherwise.

### 2.4 Authentication and authorization

Management endpoints require a valid authenticated user. The exact authentication scheme—session cookie, bearer token, or another mechanism—must be selected and documented before implementation.

For bearer authentication, the header would be:

```http
Authorization: Bearer <access-token>
```

Do not support this example as a promise until bearer authentication is chosen.

Every management operation must also verify the caller's access to the relevant workspace. Authentication alone does not authorize access to a widget or submission. Tenant scoping is enforced server-side for list, detail, update, delete and analytics operations.

Public widget endpoints do not require a platform user account. They must instead enforce widget status, request validation, rate limiting and abuse controls. A public widget ID does not grant management access.

### 2.5 Standard error response

Use one stable error envelope for API errors:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "request_id": "req_01J...",
    "details": [
      {
        "field": "name",
        "reason": "This field is required."
      }
    ]
  }
}
```

Fields:
- `error.code`: stable machine-readable code.
- `error.message`: safe, human-readable summary.
- `error.request_id`: optional request/correlation identifier for diagnostics.
- `error.details`: optional list of field-level or actionable validation details.

Never return stack traces, database errors, secrets, provider credentials or raw internal exception messages to clients. Keep detailed diagnostics in appropriately redacted server logs.

Recommended codes include:
- `VALIDATION_ERROR`
- `AUTHENTICATION_REQUIRED`
- `PERMISSION_DENIED`
- `RESOURCE_NOT_FOUND`
- `WIDGET_DISABLED`
- `RATE_LIMITED`
- `PAYLOAD_TOO_LARGE`
- `UNSUPPORTED_MEDIA_TYPE`
- `IDEMPOTENCY_CONFLICT`
- `INTERNAL_ERROR`
- `DEPENDENCY_UNAVAILABLE` only when the dependency failure actually prevents the requested operation

Use FastAPI's validation handling to produce the documented envelope rather than leaking a different framework-default error shape.

## 3. Endpoint summary

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/widgets` | Authenticated workspace user | Create a widget |
| `GET` | `/api/v1/widgets` | Authenticated workspace user | List widgets in a workspace |
| `GET` | `/api/v1/widgets/{widget_id}` | Authenticated workspace user | Get one widget |
| `PATCH` | `/api/v1/widgets/{widget_id}` | Authenticated workspace user | Update widget name/configuration/status |
| `DELETE` | `/api/v1/widgets/{widget_id}` | Authenticated workspace user | Delete or archive a widget according to the implemented policy |
| `GET` | `/api/v1/widgets/{widget_id}/submissions` | Authenticated workspace user | List submissions for a widget |
| `GET` | `/api/v1/submissions` | Authenticated workspace user | List workspace submissions |
| `GET` | `/api/v1/analytics/summary` | Authenticated workspace user | Retrieve basic workspace aggregates |
| `GET` | `/public/v1/widgets/{public_widget_id}/config` | Public | Retrieve public widget configuration |
| `POST` | `/public/v1/widgets/{public_widget_id}/submissions` | Public | Submit a lead |
| `GET` | `/widget/v1/widget.{version}.js` | Public | Retrieve a versioned widget script |
| `GET` | `/health/live` | Health probe | Process liveness |
| `GET` | `/health/ready` | Health probe | Readiness to serve requests |

The `workspace_id` source must be explicit in implementation: it may come from the authenticated user's selected workspace context or from a workspace-scoped route. Do not trust a body field alone to establish tenant ownership.

## 4. Management API

### 4.1 Create widget

`POST /api/v1/widgets`

Creates a widget in a workspace the authenticated caller is authorized to manage.

**Request headers**
```http
Content-Type: application/json
Authorization: <chosen authentication scheme>
```

**Proposed request body**
```json
{
  "workspace_id": "2aab2c8e-8a37-4c15-baf8-7ad8cc88e901",
  "name": "Contact form",
  "configuration": {
    "title": "Contact us",
    "submit_label": "Send message",
    "fields": [
      {
        "name": "name",
        "type": "text",
        "label": "Your name",
        "required": true
      },
      {
        "name": "email",
        "type": "email",
        "label": "Email address",
        "required": true
      },
      {
        "name": "message",
        "type": "textarea",
        "label": "How can we help?",
        "required": true
      }
    ]
  }
}
```

This is illustrative. The final configuration schema and supported field types must be defined in `widget_contract.md` and enforced by Pydantic/domain validation.

**Success:** `201 Created`

```json
{
  "id": "e82f2f9d-9d87-49d5-9375-8e4e0f8d3910",
  "public_id": "c5f63c35-7df1-4d0b-a3fd-0c7f0e0c4b0a",
  "workspace_id": "2aab2c8e-8a37-4c15-baf8-7ad8cc88e901",
  "name": "Contact form",
  "status": "active",
  "configuration": {},
  "config_version": 1,
  "created_at": "2026-10-18T12:30:00Z",
  "updated_at": "2026-10-18T12:30:00Z"
}
```

The empty `configuration` object above is only a placeholder for brevity; a real response returns the stored public-safe management configuration.

**Errors:** `400` or `422` for invalid input according to the selected validation convention; `401` unauthenticated; `403` unauthorized workspace; `404` if the selected workspace is intentionally concealed as not found; `409` for a conflicting resource state.

### 4.2 List widgets

`GET /api/v1/widgets`

Returns widgets visible to the authenticated caller in the selected workspace.

**Query parameters**
- `workspace_id` (required unless workspace context is established elsewhere)
- `limit` (optional; default `20`, maximum `100`)
- `cursor` (optional opaque pagination cursor)
- `status` (optional filter: `active`, `disabled`, `archived`)

Example:
```http
GET /api/v1/widgets?workspace_id=2aab2c8e-8a37-4c15-baf8-7ad8cc88e901&limit=20
```

**Success:** `200 OK`

```json
{
  "items": [
    {
      "id": "e82f2f9d-9d87-49d5-9375-8e4e0f8d3910",
      "public_id": "c5f63c35-7df1-4d0b-a3fd-0c7f0e0c4b0a",
      "workspace_id": "2aab2c8e-8a37-4c15-baf8-7ad8cc88e901",
      "name": "Contact form",
      "status": "active",
      "config_version": 1,
      "created_at": "2026-10-18T12:30:00Z",
      "updated_at": "2026-10-18T12:30:00Z"
    }
  ],
  "next_cursor": null
}
```

Return `configuration` only if needed by the management client. Avoid returning internal-only or secret fields.

### 4.3 Get widget

`GET /api/v1/widgets/{widget_id}`

Returns one widget only if it belongs to a workspace the caller may access.

**Success:** `200 OK`, with the widget response schema.

**Errors:** `401`, `403`/`404` according to the resource-concealment policy, or `404` if no visible widget exists.

### 4.4 Update widget

`PATCH /api/v1/widgets/{widget_id}`

Updates only fields explicitly supplied by the client. Omitted fields remain unchanged.

**Proposed request body**
```json
{
  "name": "Sales contact form",
  "status": "disabled",
  "configuration": {
    "title": "Contact sales",
    "submit_label": "Contact sales",
    "fields": []
  }
}
```

The example configuration is intentionally abbreviated; an empty field list should be rejected unless the product explicitly supports it.

**Success:** `200 OK`, returning the updated widget.

Rules:
- Validate the complete resulting configuration, not just the changed fragment.
- Only allow supported fields to be updated.
- Update `updated_at`.
- Increment `config_version` when cache-relevant configuration changes, if that version is used.
- A disabled or archived widget must reject new public submissions.
- Do not allow a request to transfer a widget to a different workspace unless an explicit transfer operation and authorization policy are designed.

### 4.5 Delete or archive widget

`DELETE /api/v1/widgets/{widget_id}`

The behavior must be selected before implementation. Recommended initial behavior: archive or disable the widget while preserving accepted submissions.

Possible contract:
- `204 No Content` for successful deletion/archival without a response body, or
- `200 OK` returning the updated lifecycle state.

Choose one response and use it consistently. Do not hard-delete a widget if doing so would accidentally cascade-delete historical submissions.

### 4.6 List widget submissions

`GET /api/v1/widgets/{widget_id}/submissions`

Lists submissions associated with a widget visible to the caller.

**Query parameters**
- `limit`: optional, default `20`, maximum `100`
- `cursor`: optional opaque cursor
- `created_after`: optional ISO 8601 timestamp
- `created_before`: optional ISO 8601 timestamp

**Success:** `200 OK`

```json
{
  "items": [
    {
      "id": "0e1b1a0b-c4c4-4d66-9b5e-4f3a04c65e16",
      "widget_id": "e82f2f9d-9d87-49d5-9375-8e4e0f8d3910",
      "created_at": "2026-10-18T12:35:00Z",
      "data": {
        "name": "A visitor",
        "email": "visitor@example.com",
        "message": "Please contact me."
      }
    }
  ],
  "next_cursor": null
}
```

Rules:
- Scope by the authorized workspace and the requested widget.
- Use a stable ordering, preferably `created_at DESC` with a unique ID tie-breaker.
- Do not expose internal provider responses, secrets, job payloads or unredacted internal errors.
- Apply pagination and sensible response-size limits.

### 4.7 List workspace submissions

`GET /api/v1/submissions`

Lists submissions across the authenticated user's selected workspace.

**Query parameters**
- `workspace_id` (required unless workspace context is established elsewhere)
- `widget_id` (optional filter)
- `created_after` / `created_before` (optional ISO 8601 range)
- `limit` (optional, default `20`, maximum `100`)
- `cursor` (optional opaque cursor)

**Success:** `200 OK` using the same submission item shape and pagination envelope as the widget-specific endpoint.

Validate timestamp ranges and reject a `created_after` later than `created_before`.

### 4.8 Analytics summary

`GET /api/v1/analytics/summary`

Returns basic aggregates for a workspace. Analytics must be scoped to the authorized workspace.

**Query parameters**
- `workspace_id` (required unless workspace context is established elsewhere)
- `from` (optional ISO 8601 start timestamp)
- `to` (optional ISO 8601 end timestamp)
- `widget_id` (optional filter)

**Success:** `200 OK`

```json
{
  "workspace_id": "2aab2c8e-8a37-4c15-baf8-7ad8cc88e901",
  "from": "2026-10-01T00:00:00Z",
  "to": "2026-11-01T00:00:00Z",
  "submission_count": 125,
  "submissions_by_widget": [
    {
      "widget_id": "e82f2f9d-9d87-49d5-9375-8e4e0f8d3910",
      "count": 75
    }
  ]
}
```

The values above are examples, not live data. The implementation must define whether `to` is inclusive or exclusive; a half-open range (`from <= created_at < to`) is recommended to simplify adjacent reporting windows.

## 5. Public widget API

### 5.1 Fetch public configuration

`GET /public/v1/widgets/{public_widget_id}/config`

Returns only the configuration required to render an enabled widget.

**Authentication:** none.

**Success:** `200 OK`

```json
{
  "public_widget_id": "c5f63c35-7df1-4d0b-a3fd-0c7f0e0c4b0a",
  "status": "active",
  "config_version": 1,
  "configuration": {
    "title": "Contact us",
    "submit_label": "Send message",
    "fields": [
      {
        "name": "email",
        "type": "email",
        "label": "Email address",
        "required": true
      }
    ],
    "success_message": "Thanks. Your message has been received."
  }
}
```

The example only illustrates the shape. The final public schema belongs in `widget_contract.md`.

Caching:
- Return appropriate cache headers and validators when caching is enabled.
- Never cache private management responses as public responses.
- Define how configuration updates invalidate or version cached data.

**Errors:** `404` for unknown or non-public widgets; `410 Gone` may be used for archived widgets if that policy is selected. Avoid exposing private workspace details.

### 5.2 Submit a lead

`POST /public/v1/widgets/{public_widget_id}/submissions`

Accepts a visitor submission for an enabled widget.

**Request headers**
```http
Content-Type: application/json
Origin: https://customer.example
Idempotency-Key: <optional-key-if-supported>
```

`Origin` is controlled by the browser environment and is not proof of identity. The idempotency header is optional only if the implementation supports that feature.

**Proposed request body**
```json
{
  "data": {
    "name": "A visitor",
    "email": "visitor@example.com",
    "message": "Please contact me."
  }
}
```

Do not accept authoritative `workspace_id`, internal `widget_id`, timestamps, notification states or enrichment results from the visitor.

**Success:** `201 Created` for a newly stored submission.

```json
{
  "id": "0e1b1a0b-c4c4-4d66-9b5e-4f3a04c65e16",
  "status": "accepted",
  "message": "Your submission has been received."
}
```

For a retry with the same idempotency key, return the documented replay result if idempotency is implemented. Reusing a key with a different payload should return the documented conflict response, recommended as `409 Conflict`.

**Errors**
- `400 Bad Request` or `422 Unprocessable Content`: malformed JSON or invalid field data, according to the chosen convention.
- `404 Not Found`: unknown public widget.
- `409 Conflict`: idempotency-key conflict, if supported.
- `413 Content Too Large`: request exceeds configured size limits.
- `415 Unsupported Media Type`: unsupported content type.
- `429 Too Many Requests`: rate limit exceeded; include `Retry-After` when available.
- `503 Service Unavailable`: only when a required dependency prevents the submission from being stored. Optional enrichment or notification failure after persistence must not be reported as if the lead was not captured.

The server must validate all fields against the widget configuration, apply abuse controls, persist the submission, and return a stable result. Client-side validation is only a usability feature.

### 5.3 Widget JavaScript asset

`GET /widget/v1/widget.{version}.js`

Serves the embeddable widget JavaScript bundle.

- Public, no platform authentication.
- Use immutable caching only for assets whose URL uniquely identifies their content/version.
- Set an appropriate JavaScript content type.
- Do not embed secrets or privileged credentials in the bundle.
- Document supported versions and the compatibility policy in `widget_contract.md`.

The literal route syntax must be confirmed against the FastAPI route implementation; `{version}` is a path parameter placeholder in this document.

## 6. Health endpoints

### 6.1 Liveness

`GET /health/live`

Indicates whether the API process is running.

**Success:** `200 OK`

```json
{
  "status": "alive"
}
```

Liveness should not fail merely because an optional external provider is unavailable.

### 6.2 Readiness

`GET /health/ready`

Indicates whether the instance is ready to serve its intended traffic.

**Success:** `200 OK`

```json
{
  "status": "ready"
}
```

If a required dependency such as PostgreSQL is unavailable, return a non-success status such as `503 Service Unavailable`. Keep the response minimal and do not expose connection strings or diagnostic secrets. Define which dependencies are required for readiness in the implementation.

## 7. Pagination, filtering and ordering

For list endpoints:
- Use a consistent response envelope: `items` and `next_cursor`.
- Use an opaque cursor rather than exposing internal query details.
- Apply a default page size of `20` and a maximum of `100`, unless the implementation documents different values.
- Use stable ordering: `created_at DESC` plus a unique identifier as a tie-breaker.
- Validate filters and timestamp formats.
- Scope queries to the authorized workspace before applying user-supplied filters.
- Avoid returning the entire submission history in one response.

Cursor encoding and decoding are implementation details, but clients must treat the cursor as opaque.

## 8. CORS and browser behavior

The public widget is expected to run on customer websites whose origins differ from the API origin.

- Configure CORS for the intended public widget endpoints and supported methods/headers.
- Handle preflight `OPTIONS` requests where required by the browser request shape.
- Allow only necessary methods and headers.
- If origin allowlisting is supported per widget, validate it on the server and document whether missing or opaque origins are allowed.
- CORS is a browser policy, not an authentication or abuse-prevention mechanism. Public endpoints still require server-side validation and rate limiting.
- Do not reflect arbitrary origins with credentials enabled.

The exact CORS policy must be tested from a separate origin and recorded in `widget_contract.md` and `security_spec.md`.

## 9. Rate limiting and payload limits

Public submission endpoints must have bounded resource consumption.

- Apply rate limits according to the chosen key (for example, IP and/or widget).
- Return `429 Too Many Requests` when a limit is exceeded.
- Include `Retry-After` when the reset/retry time is known.
- Bound JSON body size, field count, per-field length and total request processing time.
- Define behavior if the rate-limit store is unavailable.
- If the application is behind a reverse proxy, trust forwarded client-IP headers only from explicitly trusted proxies.

Exact thresholds and storage implementation must be set in configuration and verified with tests; do not treat illustrative values as production defaults without a decision.

## 10. HTTP status-code conventions

| Status | Meaning in this API |
|---|---|
| `200 OK` | Successful read or update returning a body |
| `201 Created` | Resource or submission created |
| `204 No Content` | Successful operation with no response body, if selected for delete |
| `400 Bad Request` | Malformed request or invalid query combination |
| `401 Unauthorized` | Missing or invalid authentication for a protected endpoint |
| `403 Forbidden` | Authenticated caller lacks permission |
| `404 Not Found` | Resource does not exist or is intentionally concealed |
| `409 Conflict` | State conflict or idempotency-key reuse with different input |
| `410 Gone` | Resource is intentionally no longer publicly available, if this convention is selected |
| `413 Content Too Large` | Request exceeds configured size limit |
| `415 Unsupported Media Type` | Unsupported request content type |
| `422 Unprocessable Content` | Valid JSON that fails schema/business validation, if this convention is selected |
| `429 Too Many Requests` | Rate limit exceeded |
| `500 Internal Server Error` | Unexpected internal failure |
| `503 Service Unavailable` | Required dependency prevents the requested operation |

Choose one consistent validation convention between `400` and `422` and use it across endpoints. Do not return `503` for optional integration failures if the primary operation has already succeeded.

## 11. Compatibility and contract testing

- Treat response field removals, field type changes, changed authentication requirements and changed status semantics as breaking changes.
- Prefer additive changes within `/v1` where they do not alter existing meaning.
- Generate or inspect FastAPI's OpenAPI document and compare it with this specification.
- Add integration tests for success, invalid input, unauthenticated access, cross-tenant access, missing resources, rate limiting, oversized payloads, CORS/preflight, idempotency (if supported), and dependency failures.
- Test that public responses never include private workspace fields or secrets.
- Update this document in the same change that updates route behavior or Pydantic request/response models.

## 12. Related documentation

- [`architecture.md`](architecture.md) — component boundaries and request paths
- [`domain_models.md`](domain_models.md) — business entities and invariants
- [`database_schema.md`](database_schema.md) — persistence schema and tenant integrity
- [`widget_contract.md`](widget_contract.md) — browser-facing embed and public configuration contract
- [`submission_flow.md`](submission_flow.md) — submission processing and failure semantics
- [`security_spec.md`](security_spec.md) — authorization, abuse controls and trust boundaries
- [`event_spec.md`](event_spec.md) — asynchronous job/event contracts, if implemented

---

## Maintenance rule

This document is the intended API contract, not a substitute for the running application. Keep endpoint paths, Pydantic schemas, status codes, authentication requirements, pagination and error responses synchronized with the implemented FastAPI routes and generated OpenAPI schema.
