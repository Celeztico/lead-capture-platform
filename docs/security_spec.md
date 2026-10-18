# Security Specification

## 1. Purpose and status

This document defines the security boundaries, threats, and required controls for the **Lead-Capture Platform**. The platform exposes authenticated workspace APIs and public endpoints that run on third-party websites, so it must protect tenant data while treating browser requests and visitor input as untrusted.

It describes what the system must protect, which controls belong at each layer, and how those controls should be verified.

> **Implementation status:** This is the initial security specification. A control described here is a requirement, not proof that it has been implemented. Mark controls as implemented only when the code, configuration and tests verify them.

## 2. Security objectives

The platform should preserve:

- **Confidentiality:** one workspace cannot read another workspace's widgets, leads or analytics; secrets and personal data are not exposed unnecessarily.
- **Integrity:** only authorized users can modify workspace resources; visitor input cannot override trusted ownership, identifiers, timestamps or processing status.
- **Availability:** public endpoints have bounded resource consumption and resist abusive request bursts.
- **Reliability of capture:** optional integration failures do not erase or misrepresent a lead that has already been stored.
- **Accountability:** security-relevant events can be investigated through safe logs and request identifiers without logging raw lead contents or credentials.

## 3. Assets and trust boundaries

### 3.1 Assets to protect

- User identities and authentication credentials.
- Workspace membership and role assignments.
- Widget configuration, including private management settings.
- Submitted lead data, which may contain personal information.
- Database credentials, signing keys, provider credentials and webhook secrets.
- Idempotency records and background-job state, if implemented.
- Service availability, database capacity and third-party provider quotas.
- Logs, traces, metrics and backups that may contain operational or personal data.

### 3.2 Trust boundaries

1. **Browser/customer website → public API:** requests, headers, payloads and rates are untrusted.
2. **Authenticated client → management API:** a valid identity does not automatically authorize access to every workspace.
3. **Application → PostgreSQL:** queries, transactions and credentials must preserve data integrity and least privilege.
4. **Application → external providers:** responses and availability are not guaranteed; provider output must be validated.
5. **Application → customer webhook destination:** a configured URL may point to an unsafe or internal network target.
6. **Application → logs/telemetry:** observability systems are separate data stores and must not receive secrets or unnecessary personal data.
7. **Deployment configuration → running service:** environment variables and secret stores must be protected from unauthorized access.

## 4. Authentication and authorization

### 4.1 Authentication

All management endpoints must require a valid authenticated platform user. The authentication mechanism must be selected and documented before implementation.

Security requirements:
- Use a maintained authentication library or a well-understood protocol; do not invent cryptographic schemes.
- If passwords are used, store only a strong password hash produced by an appropriate password-hashing algorithm. Never store plaintext passwords.
- If token-based authentication is used, validate signature, issuer/audience where applicable, expiry and other required claims.
- If cookie-based sessions are used, configure `Secure`, `HttpOnly` and appropriate `SameSite` attributes, and address CSRF risks for state-changing requests.
- Use TLS for credentials and tokens in transit outside local development.
- Define credential expiry, revocation and account-disable behavior.
- Never place credentials in URLs or logs.

Public widget configuration and submission endpoints do not require a platform user account. Their exposure must be compensated for with strict validation, rate limiting, abuse controls and limited responses.

### 4.2 Authorization

Authorization is required on every management operation, including list, detail, create, update, delete, export and analytics.

- Resolve the caller's identity from verified authentication data.
- Check that the caller has the required workspace membership or ownership.
- Apply workspace scope to database queries rather than fetching a resource globally and relying on the UI to hide it.
- Enforce role requirements for sensitive actions if roles are implemented.
- Return a consistent `403` or intentionally concealed `404` according to the chosen resource-disclosure policy.
- Never treat possession of a UUID or public widget ID as permission to access a resource.

The exact authentication mechanism and role model are implementation decisions; the authorization guarantees are not optional.

## 5. Tenant isolation

Tenant isolation is a primary security invariant.

### Required controls

1. Every widget belongs to one workspace.
2. Every submission belongs to its widget's owning workspace.
3. The backend derives public submission ownership from the resolved widget record.
4. Protected queries include the authorized workspace scope.
5. Updates and deletes verify both resource identity and workspace authorization.
6. Analytics, exports and submission lists use the same scope rules.
7. Database constraints should prevent inconsistent `workspace_id` and `widget_id` relationships where practical.
8. Cross-tenant access tests cover every resource type and operation.

### Common failure mode

A route such as `GET /api/v1/widgets/{widget_id}` is unsafe if it queries only by `widget_id` and never checks workspace access. A hard-to-guess identifier does not solve this problem.

### Verification

Create two test workspaces with separate users, widgets and submissions. Attempt to read, update, delete, list and query analytics for the other workspace's resources. Verify that no data leaks and no cross-tenant mutation succeeds.

## 6. Public endpoint abuse protection

The public submission endpoint is intentionally reachable without platform authentication and is therefore a primary abuse surface.

### 6.1 Rate limiting

Apply rate limits before expensive operations and external provider calls.

Possible limit dimensions:
- Client IP address.
- Public widget ID.
- A combination of IP and widget.
- Additional dimensions if the product later supports account-level quotas.

Requirements:
- Return `429 Too Many Requests` when a limit is exceeded.
- Include `Retry-After` when a retry interval is known.
- Keep the limiter's storage and outage behavior explicit.
- Avoid using arbitrary `X-Forwarded-For` values unless requests arrive through a configured trusted proxy.
- Test that a burst is limited while ordinary traffic continues to work.

Choose thresholds using tests and deployment capacity rather than treating undocumented values as universal defaults. If the rate-limit store fails, use an explicit fail-open or fail-closed policy based on the threat model.

### 6.2 Spam prevention

Use a layered approach rather than relying on one signal:
- Request rate limits.
- Strict payload and field limits.
- Honeypot or other low-friction checks, if implemented.
- Detection of clearly malformed or repeated patterns.
- Optional stronger challenges only if justified by observed abuse.

Do not trust client-side checks as an abuse-control boundary. Avoid revealing detailed internal spam rules in public error responses.

### 6.3 Resource limits

Enforce limits for:
- Request body size.
- Number of submitted fields.
- Per-field text length.
- Configuration size and number of widget fields.
- Request processing time.
- External-provider connection and response time.
- Retry count and total retry window for background work.

Return a documented client error for oversized input. Bound concurrency and database work so one public request cannot consume unbounded resources.

## 7. Input validation and injection prevention

Validate input at the HTTP boundary and enforce business invariants in the application layer.

- Parse only supported content types and reject malformed JSON.
- Validate request and response schemas using explicit Pydantic models.
- Allow only configured widget field names and supported field types.
- Enforce field-specific type and length rules.
- Normalize values only where semantics are clear.
- Do not trust client-supplied `workspace_id`, internal `widget_id`, timestamps, status values or enrichment results.
- Use SQLAlchemy/parameterized database operations; never concatenate untrusted input into SQL.
- Avoid evaluating configuration as JavaScript or injecting arbitrary HTML.
- Render labels, placeholders, success messages and visitor input as text by default.
- If HTML rendering is ever supported, define and enforce a safe allowlist/sanitization policy.
- Validate URLs and destinations before server-side requests.
- Keep error responses generic enough to avoid exposing database internals.

Client-side validation is a usability feature only. Every security-relevant check must be enforced server-side.

## 8. CORS and origin handling

The widget is expected to run on customer websites with origins different from the platform API.

Requirements:
- Configure CORS only for the methods, headers and endpoints the widget requires.
- Handle browser preflight `OPTIONS` requests where necessary.
- Do not reflect arbitrary origins when credentials are enabled.
- Do not allow credentials on public endpoints unless there is a documented requirement and a safe policy.
- If per-widget origin allowlists are supported, compare origins using a documented normalization and matching rule.
- Define behavior for missing or opaque origins.
- Test allowed and disallowed origins from a separate browser origin.

**CORS is not authentication.** Non-browser clients can call public endpoints directly and can forge `Origin` headers. CORS must be paired with rate limiting, validation and spam controls.

## 9. Idempotency, replay and duplicate requests

Network timeouts can cause a client to retry a request whose first attempt may already have succeeded.

If idempotency is implemented:
- Scope keys clearly, for example by widget.
- Enforce uniqueness in the database for the chosen key scope.
- Compute a server-side fingerprint of the relevant request data.
- Return the prior result for the same key and same payload according to the API contract.
- Return a conflict if the same key is reused with a different payload.
- Make concurrent duplicate requests safe using database transactions and constraints.
- Define expiry and cleanup behavior.
- Do not store raw sensitive payloads in the idempotency table when a fingerprint and result reference are sufficient.

Without a tested idempotency mechanism, duplicate submissions remain possible after ambiguous network failures. Do not claim exactly-once processing.

For background jobs and external notifications, use bounded retries and idempotent side-effect handling where practical. A retry policy alone does not prevent duplicate email or webhook delivery.

## 10. External integrations and SSRF

### 10.1 Geolocation providers

- Apply explicit timeouts.
- Validate provider responses before using or persisting them.
- Send only the minimum data needed for enrichment.
- Attempt provider B when provider A fails according to the defined fallback policy.
- If both providers fail after persistence, preserve the lead and continue without enrichment.
- Avoid exposing provider errors or credentials to visitors.

### 10.2 Email provider

- Store credentials in secret configuration.
- Use TLS where supported.
- Apply timeouts and bounded retry behavior.
- Do not log API keys or full message bodies containing lead data.
- Treat notification failure as a side-effect failure, not a submission-persistence failure.

### 10.3 Customer webhooks

If the product allows workspace users to configure webhook destinations, the backend becomes a potential server-side request forgery (SSRF) target.

Before enabling arbitrary destinations:
- Require valid URL schemes and reject unsupported schemes.
- Block loopback, link-local, private and reserved IP ranges unless an explicitly approved internal integration requires them.
- Resolve hostnames safely and guard against DNS rebinding and redirect-based bypasses.
- Revalidate redirect targets or disable redirects.
- Apply egress restrictions at the network layer where possible.
- Set connection/read timeouts and response-size limits.
- Sign webhook requests if the contract supports signatures, and document signature verification for consumers.
- Store webhook secrets securely and never expose them in public widget configuration.
- Redact sensitive headers and response bodies from logs.

Do not claim webhook SSRF protection until the destination-validation code and tests exist.

## 11. Secret and configuration management

Secrets may include database credentials, authentication signing keys, email API keys, geolocation API keys, webhook signing secrets and queue credentials.

Requirements:
- Read secrets from environment-based configuration or a managed secret store.
- Commit only safe placeholders in `.env.example`.
- Never commit real `.env` files, private keys, tokens or provider credentials.
- Validate required configuration at startup and fail clearly if missing or invalid.
- Keep secrets out of browser JavaScript, public widget configuration, API responses and URLs.
- Restrict production secret access to the minimum required services and people.
- Rotate credentials after suspected exposure and document the process.
- Separate development, test and production credentials.
- Redact sensitive configuration values in diagnostics.

## 12. Personal data and privacy

Lead submissions can contain personal information. Treat them as sensitive business data even if the initial project is a prototype.

- Collect only fields the widget is configured to request.
- Document the purpose for each category of data.
- Minimize personal data sent to geolocation, email and webhook providers.
- Do not log raw submissions, authentication tokens or provider credentials.
- Avoid placing personal data in URLs, metrics labels, request IDs or exception messages.
- Restrict submission access to authorized workspace users.
- Define retention, export and deletion behavior before production use.
- Consider whether IP addresses, origin metadata and location results are stored, why they are needed, and how long they are retained.
- Protect backups and operational systems that contain lead data.
- Ensure public error messages do not reveal whether unrelated users or workspaces exist.

This document does not make a legal-compliance claim. Applicable privacy obligations depend on deployment location, data collected and how the service is operated.

## 13. Security-relevant logging and monitoring

Log enough context to investigate suspicious activity while minimizing sensitive data.

Recommended fields:
- Request/correlation ID.
- Route and method.
- Safe internal widget/workspace reference where appropriate.
- Outcome and HTTP status.
- Latency and processing stage.
- Rate-limit decision category.
- Authentication/authorization failure category.
- Persistence and provider outcome categories.
- Background job ID and attempt count, if implemented.

Do not log:
- Passwords, access tokens, cookies or authorization headers.
- Raw form bodies or unnecessary contact details.
- Webhook signing secrets or provider API keys.
- Unredacted provider responses containing personal information.
- Full internal exception details in client-facing responses.

Monitor abnormal rates of rejected submissions, `429` responses, authorization failures, database errors, provider failures and repeated job retries where telemetry is available. Avoid high-cardinality or personally identifying metric labels.

## 14. Security controls by layer

| Layer | Required controls | Verification |
|---|---|---|
| HTTP/API boundary | Authentication dependencies, schema validation, content-type and body-size checks, stable errors | API tests for missing auth, malformed input and oversized payloads |
| Authorization/service | Workspace access checks, widget-state checks, server-side business rules | Cross-tenant and invalid-state tests |
| Persistence | Foreign keys, unique constraints, safe query construction, transaction boundaries | Migration review and database integration tests |
| Public abuse controls | Rate limiting, spam checks, bounded processing | Burst tests and abuse-case tests |
| Browser integration | Narrow CORS, safe DOM rendering, no embedded secrets | Cross-origin tests and widget review |
| External adapters | Timeouts, response validation, bounded retries, fallback | Deterministic provider failure tests |
| Configuration | Secret isolation, startup validation, environment separation | Configuration tests and repository secret scanning |
| Logging/operations | Redaction, correlation IDs, safe diagnostics | Tests or checks that ensure sensitive values are absent |

## 15. Minimum security test checklist

Before declaring the core security requirements complete, test:

- [ ] Unauthenticated callers cannot use protected management endpoints.
- [ ] Authenticated users cannot read or mutate another workspace's widgets.
- [ ] Cross-tenant submission and analytics queries do not leak data.
- [ ] Public IDs do not grant management access.
- [ ] Disabled and archived widgets reject new submissions.
- [ ] Malformed JSON, unsupported media types and oversized bodies are rejected.
- [ ] Unknown fields and invalid field types follow the documented policy.
- [ ] SQL injection-style input is treated as data and cannot alter queries.
- [ ] Widget configuration cannot inject executable HTML or JavaScript.
- [ ] Rate limits return `429` under a controlled burst.
- [ ] Origin/CORS behavior matches the documented policy.
- [ ] Idempotency concurrency and conflicting-key behavior are tested if supported.
- [ ] Provider failures do not erase stored submissions.
- [ ] Webhook destination validation blocks prohibited destinations before webhooks are enabled.
- [ ] Secrets and raw lead data do not appear in client errors or logs.
- [ ] Required configuration fails safely when missing.
- [ ] Security-relevant failure cases produce safe diagnostic context.

## 16. Residual risks and implementation decisions

The following must be explicitly resolved before production deployment:

- Authentication mechanism, session/token lifecycle and account recovery.
- Workspace membership and role model.
- Exact rate-limit thresholds, storage backend and outage policy.
- Spam signals and false-positive handling.
- Per-widget origin allowlisting policy, if any.
- Idempotency key scope, expiry and replay semantics.
- Webhook destination policy, signing and SSRF protections.
- Lead-data retention, deletion and export.
- Backup protection and credential rotation.
- Production TLS, database network access and service permissions.

A residual-risk register can track unresolved items, but it does not replace implementing the controls.

## 17. Related documentation

- [`architecture.md`](architecture.md) — components and trust boundaries
- [`domain_models.md`](domain_models.md) — ownership and business invariants
- [`database_schema.md`](database_schema.md) — constraints and tenant integrity
- [`api_contracts.md`](api_contracts.md) — authentication, errors and endpoint behavior
- [`widget_contract.md`](widget_contract.md) — browser-facing behavior and CORS
- [`submission_flow.md`](submission_flow.md) — validation, abuse controls, persistence and failure policy

---

## Maintenance rule

Update this specification when a security boundary, threat, control or data-handling behavior changes. Distinguish required controls from implemented controls, and mark a control as implemented only after the relevant code, configuration and tests provide evidence.
