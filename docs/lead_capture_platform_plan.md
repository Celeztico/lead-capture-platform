# Lead-Capture Platform --- Production Evolution Plan

**Project type:** Backend-first SaaS / embeddable widget platform\
**Primary stack:** Python, FastAPI, PostgreSQL, Docker\
**Status:** Planning baseline --- update this document as implementation
decisions become real\
**Version:** 1.0\
**Purpose:** Guide the internship capstone, define the initial product
boundary, and provide a controlled path toward a useful,
production-oriented service and cloud-engineering portfolio project.

------------------------------------------------------------------------

## 1. Project vision

Build a service that lets a website owner create an embeddable widget
(initially a contact/lead-capture form), install it with one script tag,
receive submissions safely, and review submissions and basic analytics
in an authenticated dashboard/API.

The system must treat public browser traffic as untrusted. It should
validate inputs at the boundary, isolate each customer's data, limit
abuse, handle upstream dependency failures, and keep secondary work such
as email/webhooks from breaking successful submission storage.

After the internship submission, evolve the same codebase deliberately
into a deployed SaaS-style application. Later phases may add distributed
rate limiting, a durable queue, observability, infrastructure as code,
stronger tenant administration, privacy workflows, and cloud deployment.
These later additions must not be represented as internship
requirements.

### Product mission

> Help small websites and independent developers collect leads or
> feedback using a lightweight, configurable widget, without having to
> build and operate their own form backend.

### Intended users

-   **Workspace owner:** creates widgets and reviews submissions.
-   **Website visitor:** fills in a public widget; does not need an
    account.
-   **Operator/developer:** deploys, monitors, troubleshoots, and
    maintains the service.
-   **Future team member:** may manage a workspace with explicitly
    granted permissions (later phase).

### Product value

-   A single script snippet embeds a form on another website.
-   Form submissions are validated, stored, and associated with the
    correct widget/workspace.
-   Abuse controls reduce spam and request floods.
-   Optional enrichment adds approximate location information where
    available.
-   Email and webhook failures do not erase a valid submission.
-   Owners can inspect submissions and simple aggregate statistics.
-   The architecture can later be deployed and operated on cloud
    infrastructure.

### Success criteria

**Internship success** 1. Every required acceptance probe in the
Lead-Capture Platform brief passes. 2. A clean checkout can be started
using documented commands and seeded with demo data. 3. The public
widget works from a different origin than the API. 4. Automated tests
prove the key failure, security, and idempotency behaviors. 5. Required
submission documents and evidence are complete.

**Product success after the internship** 1. A public demo deployment is
reachable and has a clear limitations/privacy statement. 2. A test user
can create a widget, embed it on a separate site, submit a form, and see
the result in the dashboard/API. 3. Operators can identify errors and
dependency failures without exposing secrets or submitted personal data.
4. Deployments and schema changes are repeatable, documented, and
recoverable. 5. New features are added without weakening tenant
isolation or the public submission path.

------------------------------------------------------------------------

## 2. Scope and source alignment

This plan deliberately separates the original internship scope from
later product improvements.

### 2.1 Internship baseline --- required core

The Lead-Capture Platform brief defines the following core:

-   Authenticated CRUD for widgets.
-   Multi-tenant isolation for widgets and submissions.
-   A generated embed snippet.
-   Public widget JavaScript and public widget configuration endpoints.
-   Appropriate HTTP caching for config and versioned widget assets.
-   A widget that renders on a page served from a different origin.
-   A public submission endpoint with correct CORS and preflight
    handling.
-   Boundary validation, clean JSON errors, and rejection of
    malformed/oversized payloads.
-   Safe persistence of valid submissions.
-   Rate limiting per IP and/or widget, returning `429` under a burst
    while normal traffic continues to work.
-   At least one demonstrable spam-prevention technique.
-   Geolocation enrichment with provider A → provider B fallback.
-   Submission success even when all geo providers fail.
-   A failing email/webhook side effect must not prevent the submission
    being stored.
-   An owner-facing dashboard API with submission lists and basic
    aggregates.
-   Required repository documentation and evidence.

The brief also establishes a three-path mental model: authenticated
owner management, public cached widget delivery, and public protected
submission. Preserve that separation.

### 2.2 Shared backend requirements to retain

The capstone brief lists these shared expectations. Treat them as
required engineering properties, not optional polish:

-   Layered architecture separating data, logic, and HTTP.
-   Validation at the boundary; invalid input should produce a clean
    `4xx`, not an accidental `500`.
-   At least one background job for slow/bulk work, with retries and a
    failure alert.
-   Real persistence with migrations, suitable indexes, and tenant
    isolation.
-   Idempotency where it matters.
-   Secrets supplied through environment/configuration, not committed or
    logged.
-   If AI is ever introduced, record cost per call and enforce a budget
    guard. **AI is not part of this project's core.**

### 2.3 Explicitly out of scope for internship submission

Do not let these block the core submission:

-   A polished production frontend or a full drag-and-drop form builder.
-   Kubernetes, microservices, multi-region architecture, or
    autoscaling.
-   Real payment processing or billing.
-   A custom analytics warehouse.
-   Guaranteed delivery of email/webhooks before a durable queue exists.
-   Complex enterprise RBAC.
-   CAPTCHA integration unless chosen as the one spam-control
    implementation or later stretch.
-   Marketing automation, CRM replacement, or a large integration
    marketplace.

### 2.4 Product-specific additions (my own contribution)

The initial additions should be modest, visible, useful, and testable.
They should not replace or conflict with the rubric.

**Own additions for the first release:** 1. **Submission idempotency:**
accept an optional idempotency key from the widget/client and prevent
accidental duplicate storage when the same submission is retried. Define
key scope, expiry/retention, and conflict behavior. 2. **Privacy-first
data handling:** document what data is collected; avoid storing raw IP
longer than necessary; keep enrichment fields optional; provide a basic
workspace export and deletion path if time allows after core acceptance.
3. **Operational health endpoints:** separate liveness and readiness
checks, with readiness verifying required dependencies without leaking
internal details. 4. **Deterministic failure tests:** make geo-provider
and notification failures injectable in tests, so fallback and
graceful-degradation behavior is reproducible. 5. **Submission lifecycle
metadata:** record received/processed timestamps and a minimal
processing status for secondary actions, without making a successful
form submission depend on them. 6. **Developer-friendly API errors:**
consistent error shape, stable error codes, and a request/correlation
ID.

Mark each addition in `DECISIONS.md` and `EVIDENCE.md` when implemented.
Do not claim an addition is complete until code and tests prove it.

------------------------------------------------------------------------

## 3. Architecture principles

1.  **Modular monolith first.** One FastAPI application and one
    repository, with clear modules. Split services only when a
    demonstrated need justifies it.
2.  **Database is the source of truth.** Use PostgreSQL for persisted
    product data. Redis and queues are later additions, not requirements
    for the first milestone.
3.  **Separate the three request paths.** Owner API, public widget
    delivery, and public submission have different trust and caching
    needs.
4.  **Fail closed on authorization; degrade gracefully on optional
    dependencies.** A user must never access another tenant's data. Geo,
    email, and webhook failures must not invalidate an already accepted
    submission.
5.  **Make correctness observable.** Important behaviors must have
    tests, structured logs, metrics later, and evidence.
6.  **Prefer explicit contracts.** Define request/response schemas,
    status codes, data ownership, retries, and idempotency before
    implementing them.
7.  **Minimize collected data.** Collect only fields configured by the
    widget. Treat submission content and IP addresses as sensitive.
8.  **Secure defaults.** No wildcard CORS for authenticated APIs, no
    secrets in Git, no raw user content in logs, and no public access to
    private dashboard endpoints.
9.  **Build in vertical slices.** Keep the main branch runnable and
    deliver a working end-to-end path early.
10. **Infrastructure follows product needs.** Add Redis, a queue, cloud
    resources, and orchestration only when a phase gives them a clear
    purpose.

### Logical architecture

``` text
Website owner
   │ authenticated
   ▼
Owner API ────────────────► PostgreSQL
   │                         ▲
   └─ creates widget/snippet │
                             │
Website visitor              │
   │ loads versioned script  │
   ▼                         │
Public widget config/API     │
   │                         │
   └─ submits form ─► validation / abuse controls
                              │
                              ├─► persist submission (primary outcome)
                              │
                              ├─► optional geo enrichment (provider A → B)
                              │
                              └─► secondary email/webhook action
                                   (failure must not undo stored submission)

Owner dashboard API ◄────────┘
```

This is a logical view, not a promise that every operation is
synchronous. The internship implementation may use a simple
background-job mechanism for secondary work; the post-internship
architecture can move it to a durable queue.

------------------------------------------------------------------------

## 4. Technology baseline

Use the technologies already aligned with the backend track and prior
assignments unless a documented reason requires a change.

  -----------------------------------------------------------------------
  Area                    Initial choice          Later option
  ----------------------- ----------------------- -----------------------
  Language/API            Python + FastAPI        Keep unless there is a
                                                  strong reason to change

  Validation              Pydantic                Continue using explicit
                                                  request/response
                                                  schemas

  Database                PostgreSQL              Managed PostgreSQL in
                                                  cloud

  ORM/data access         SQLAlchemy 2.x or a     Keep migrations and
                          consistent equivalent   query ownership clear

  Migrations              Alembic                 CI migration checks and
                                                  controlled deploy
                                                  migrations

  Local environment       Docker Compose          Container registry and
                                                  cloud runtime

  Tests                   pytest +                Integration, contract,
                          HTTPX/TestClient        load, and security
                                                  tests

  Rate limiting           Local/simple            Redis-backed
                          implementation          distributed limiter
                          acceptable for core     

  Background jobs         Minimal persistent      Durable queue, retry
                          job/worker approach     policy, dead-letter
                          sufficient for the      handling
                          shared requirement      

  Widget                  Small vanilla           Versioned production
                          JavaScript bundle       build and CDN

  API documentation       FastAPI OpenAPI plus    Versioned public API
                          README                  docs

  CI                      GitHub Actions or       Build, scan, deploy,
                          equivalent              and rollback workflow

  Observability           Structured logs and     Metrics, traces,
                          health endpoints        dashboards, alerts
                          initially               

  Infrastructure          Local Docker Compose    Terraform and a cloud
                          first                   provider

  Secrets                 `.env` locally; secret  Cloud secret manager /
                          values never committed  workload identity
  -----------------------------------------------------------------------

**Version policy:** pin dependencies, update deliberately, and document
supported versions. Do not copy arbitrary version numbers into this
plan; record the actual versions selected in `pyproject.toml`, lock
files, and the technical design document.

------------------------------------------------------------------------

## 5. Data model --- initial design target

The final schema must be decided in `docs/architecture/data-model.md`
before implementation. This is a starting proposal, not a substitute for
the schema design.

### Core entities

-   **Workspace/Tenant:** customer boundary; owns widgets and
    submissions.
-   **User:** authenticated principal.
-   **WorkspaceMembership** (can be deferred if single-owner auth is
    simpler for the core): maps users to workspaces and roles.
-   **Widget:** public identifier, workspace owner, type, title,
    description, enabled/disabled state, configurable fields,
    button/display configuration, timestamps, and version.
-   **Submission:** workspace and widget references, validated field
    payload, received timestamp, optional enrichment fields, minimal
    processing status, and privacy/retention metadata.
-   **IdempotencyRecord:** key, tenant/widget scope, request
    fingerprint, resulting resource/status, created/expiry timestamps.
-   **BackgroundJob / OutboxEvent:** only as required by the chosen job
    approach; records work that must be retried and its state.
-   **WebhookEndpoint** (can be added after core): workspace, URL,
    signing secret reference, enabled state, and event subscriptions.
-   **WebhookDelivery** (later or basic initial implementation): event
    ID, attempt count, next retry, response summary, and final status.

### Data rules

-   Every tenant-owned record has a workspace/tenant key.
-   Every owner query is scoped by the authenticated workspace; never
    rely on frontend filtering.
-   Use foreign keys and database constraints to reinforce application
    rules.
-   Index common access paths, such as workspace + created time,
    widget + created time, and idempotency scope + key.
-   Store money nowhere in the core unless a future billing phase
    introduces it.
-   Do not store arbitrary unbounded request bodies.
-   Keep schema changes in migrations, never manual-only database edits.
-   Decide whether submission fields are JSONB or normalized rows based
    on the field model; document the trade-off.
-   Define deletion/retention behavior before collecting real users'
    personal data.

------------------------------------------------------------------------

## 6. API surface --- planning inventory

The design document should finalize paths, schemas, status codes,
authentication, and versioning. Names below are illustrative and may be
changed consistently before implementation.

### Authenticated owner API

-   `POST /api/v1/widgets` --- create widget.
-   `GET /api/v1/widgets` --- list current workspace widgets.
-   `GET /api/v1/widgets/{widget_id}` --- retrieve one widget.
-   `PATCH /api/v1/widgets/{widget_id}` --- update widget.
-   `DELETE /api/v1/widgets/{widget_id}` --- delete or disable widget
    according to documented retention rules.
-   `GET /api/v1/widgets/{widget_id}/embed` --- return snippet and
    integration instructions.
-   `GET /api/v1/widgets/{widget_id}/submissions` --- paginated
    submissions.
-   `GET /api/v1/analytics/summary` --- basic counts and time-series
    aggregates.
-   `GET /api/v1/health/live` --- liveness.
-   `GET /api/v1/health/ready` --- readiness.

### Public widget delivery

-   `GET /widget/v1/widget.{version}.js` --- versioned script asset.
-   `GET /public/v1/widgets/{public_widget_id}/config` --- only safe
    public rendering configuration.
-   `OPTIONS` handling for relevant cross-origin requests.

Public config must never expose workspace-private fields, secret tokens,
notification settings, internal IDs that are not needed, or private
analytics.

### Public submission

-   `POST /public/v1/widgets/{public_widget_id}/submissions` --- accept
    a configured form submission.
-   Optional request idempotency key/header, with a documented policy.
-   Return a stable response that does not reveal whether private
    workspace data exists beyond what the public flow needs.

### Later APIs

-   Webhook endpoint management and delivery history.
-   Workspace members and roles.
-   Export/deletion requests.
-   API keys and scoped programmatic access.
-   Audit log.
-   Billing/usage API only if product direction justifies it.

### API contract rules

-   Use consistent JSON error responses, for example
    `{"error":{"code":"VALIDATION_ERROR","message":"...","request_id":"..."}}`.
-   Never return stack traces or secret/internal values.
-   Use `400`/`422` for invalid input according to a documented
    consistent convention, `401` for unauthenticated requests, `403` for
    authenticated but unauthorized actions, `404` where resource
    visibility policy requires it, `413` for oversized payloads, and
    `429` for rate limits.
-   Use `201` for created resources and appropriate `2xx` responses for
    successful operations.
-   Document pagination, maximum page size, sorting, and date/time
    format.
-   Use UTC timestamps internally and ISO 8601 in the API.
-   Version public contracts deliberately; avoid changing the widget
    protocol without compatibility planning.

------------------------------------------------------------------------

## 7. Development phases --- internship core

The order follows the capstone brief's design → hardened submission path
→ delivery/dashboard/proof structure. The phases below add explicit
gates, tests, and project-specific additions. The time ranges are
estimates, not deadlines.

### Phase 0 --- Repository and working agreement

**Goal:** establish a clean, reviewable project before feature work.

**Work** - Create a dedicated public repository, following the brief's
naming convention, e.g. `flyrank-capstone-widget-platform`. - Add
`README.md`, `.gitignore`, `.env.example`, `BUILDLOG.md`, `EVIDENCE.md`,
and `capstone.yaml` as applicable to the brief. - Add a license and a
minimal project skeleton. - Establish branch/commit conventions and keep
`main` runnable. - Configure formatting/linting and a basic test
command. - Confirm that environment files, database files, keys, tokens,
and generated artifacts are ignored.

**Gate** - A clean clone can follow the documented setup. - No secret is
committed. - The application starts and the test command runs, even if
there are no features yet.

**Evidence** - Initial repository tree, startup output, test output, and
`.gitignore` review.

### Phase 1 --- Design and threat model

**Goal:** make the product boundary and critical contracts explicit
before implementing behavior.

**Work** - Write a one-page product/design summary: problem, users, data
model, API surface, layer sketch, and one explicit non-goal. - Define
tenant/workspace ownership and authorization rules. - Define the three
paths: owner management, public widget delivery, public submission. -
Draft data schema and indexes. - Define payload size limits, field
types/count limits, request timeouts, and maximum configured widget
size. - Define CORS policy for local development and intended
deployment. - Choose the core spam control (honeypot is a suitable
baseline). - Define geo fallback behavior and how providers are mocked
in tests. - Define what counts as a successful submission if
geo/email/webhook fails. - Define initial idempotency semantics and
privacy/retention assumptions. - Write a lightweight threat model:
cross-tenant access, public endpoint abuse, injection, oversized input,
leaked secrets, forged webhooks, and accidental personal-data logging. -
Document architecture decisions in `docs/decisions/` or `DECISIONS.md`.

**Gate** - `docs/design.md` and `docs/architecture/data-model.md` exist
and match the planned scope. - Every public endpoint has an owner,
request schema, response schema, auth model, and error policy. - One
explicit non-goal is documented.

**Evidence** - Design docs committed; review checklist signed off in
`EVIDENCE.md`.

### Phase 2 --- Walking skeleton and persistence

**Goal:** establish a runnable layered FastAPI application with real
persistence and migrations.

**Work** - Create modules for HTTP routes, schemas, services/business
logic, repositories/data access, models, configuration, and background
jobs. - Configure PostgreSQL with Docker Compose for local
development. - Add database migrations and a repeatable migration
command. - Implement health endpoints and configuration validation. -
Add seed/demo data command. - Add a minimal authenticated route and a
minimal database-backed widget route. - Add structured logging with
request/correlation ID; do not log secrets or raw submission bodies. -
Add unit and integration test scaffolding.

**Gate** - One end-to-end API request reaches service logic, persists to
PostgreSQL, and returns a validated response. - Fresh database setup and
migrations work from a clean checkout. - Tests run against a predictable
test database.

**Evidence** - Migration output, seeded data, API response, and test
run.

### Phase 3 --- Authentication, widget management, and tenant isolation

**Goal:** implement the private owner-facing core safely.

**Work** - Implement authenticated widget CRUD. - Select a
straightforward authentication approach appropriate to the internship
scope and document token/session handling. - Validate widget type,
title/description lengths, field count, allowed field types, required
flags, and configuration size. - Generate an opaque public widget
identifier distinct from private database IDs. - Enforce workspace
scoping in every read, update, delete, and aggregate query. - Return
consistent error responses. - Add pagination and bounded page sizes for
list endpoints. - Add database constraints and indexes. - Test
cross-tenant access attempts for widgets and submissions.

**Gate** - Authenticated owner can create/read/update/delete their
widget. - Unauthenticated access is rejected. - Tenant A cannot read,
update, delete, or query tenant B's data, including by guessing IDs. -
Invalid widget configuration returns clean `4xx` errors.

**Evidence** - Positive CRUD tests, unauthorized tests, cross-tenant
tests, validation tests.

### Phase 4 --- Public widget delivery and embed experience

**Goal:** make the product demonstrably usable on a separate website
origin.

**Work** - Generate the one-line embed snippet. - Build a minimal
JavaScript loader and form renderer; keep the UI intentionally small. -
Deliver only public-safe widget configuration. - Add cache headers to
configuration responses with a short, documented lifetime. - Serve a
versioned widget script URL or a robust cache-busting URL. - Define
cache invalidation/version behavior when widget configuration changes. -
Add a plain HTML demo site served on a different local origin/port. -
Configure CORS only for the public endpoints that need it; do not use
permissive CORS as a substitute for authorization. - Ensure the widget
has basic accessible labels and understandable success/error states. -
Test script load, config fetch, form render, and submit from the
separate origin.

**Gate** - A stranger can copy the generated snippet into the demo page
and see the widget. - Cache headers and script versioning can be
inspected and explained. - No private settings are present in public
configuration.

**Evidence** - Demo steps, browser/network proof, response headers, and
public-config security test.

### Phase 5 --- Hardened public submission path

**Goal:** accept valid submissions and reject bad traffic predictably.

**Work** - Implement the public submission endpoint. - Validate
submitted fields against the current widget configuration on the server;
never trust client-side validation alone. - Reject unknown fields, wrong
types, missing required values, malformed payloads, and oversized
requests. - Enforce limits on request body size, field count, string
length, and submission frequency. - Add rate limiting per IP and/or
widget. Document proxy/IP handling so forwarded headers are not blindly
trusted. - Add a honeypot spam control and test it. - Add optional
idempotency handling for retries; bind keys to widget/scope and a
request fingerprint. A reused key with a different payload must have
defined behavior. - Persist accepted submissions with workspace/widget
ownership. - Ensure logs omit sensitive field values and avoid
unnecessary raw-IP retention. - Add deterministic tests for normal
submissions, invalid input, oversized payloads, rate-limit bursts,
honeypot detection, and retries.

**Gate** - Valid cross-origin submission is stored and returns
success. - Invalid and oversized input returns clean `4xx` JSON errors,
never an accidental `500`. - A burst triggers `429`, and legitimate
traffic can still succeed afterward. - The spam control blocks a
demonstrable bot-like submission. - Retries do not create duplicate
submissions when the idempotency contract applies.

**Evidence** - Automated test output and representative HTTP transcripts
for every scenario.

### Phase 6 --- Enrichment, safe side effects, and background work

**Goal:** enrich accepted submissions when possible without making
optional services a single point of failure.

**Work** - Implement geo enrichment with provider A followed by provider
B. - Add strict connect/read timeouts, response validation, and bounded
retry behavior for external providers. - Do not call external services
indefinitely or let provider latency hold the public request open
unnecessarily. - If both providers fail, store the submission without
geo data. - Implement email/webhook notification as a secondary side
effect. - Ensure a notification failure does not roll back or misreport
a stored submission. - Meet the shared requirement for at least one
background job with retry and failure-alert behavior. For the internship
core, use the simplest persistent approach that satisfies restart/retry
requirements; do not claim in-memory fire-and-forget is durable. - Track
minimal job/notification state and attempt count. - Make provider and
notification failures injectable for deterministic tests. - Ensure retry
operations are idempotent or use stable event/delivery IDs.

**Gate** - Provider A failure → provider B succeeds → submission stored
with enrichment. - Both providers fail → submission still stored without
geo data. - Email/webhook failure → submission remains stored and public
response behavior remains correct. - Background work can retry after a
failure, and exhausted failures are visible through logs/status or a
documented alert mechanism.

**Evidence** - Deterministic fallback tests, side-effect failure tests,
worker retry test, and failure logs without sensitive payloads.

### Phase 7 --- Owner dashboard API and basic analytics

**Goal:** allow the workspace owner to inspect collected submissions and
understand basic activity.

**Work** - Implement paginated, tenant-scoped submission listing. - Add
filters such as widget, date range, and processing status with bounded
query complexity. - Add aggregate endpoints: submission count over time,
per-widget counts, and geo breakdown when available. - Define empty-data
behavior and consistent timezone handling. - Add indexes based on actual
query patterns. - Ensure analytics never aggregate across tenants. - Add
a minimal table/demo page only if useful; backend correctness remains
the priority. - Add a simple export path only if it fits the core
schedule; otherwise put export in a post-internship phase.

**Gate** - Owner can submit a test form and see the submission in the
correct workspace. - Counts match seeded/test data. - Cross-tenant
analytics are impossible through the API. - Pagination and filters have
documented limits.

**Evidence** - API transcripts and tests comparing expected aggregates
to actual results.

### Phase 8 --- Hardening, acceptance evidence, and internship submission

**Goal:** prove the brief is satisfied and make the repository easy for
a reviewer to run.

**Work** - Run the full test suite from a clean environment. - Verify
all required acceptance probes in the Lead-Capture brief. - Complete
`README.md`, architecture diagram, exact setup/run/seed/test commands,
API docs, limitations, and known risks. - Complete `capstone.yaml` with
the run/seed/test/base URL and endpoints as required by the brief. -
Complete `EVIDENCE.md` with one proof per requirement. - Complete
`BUILDLOG.md` honestly, noting AI help, mistakes, corrections, and what
you learned. - Check secret handling, CORS, auth, tenant isolation,
error responses, dependency timeouts, and logs. - Ensure `main` remains
runnable and all work is committed with meaningful messages. - Do not
add major new features until the required checklist is green.

**Gate** - Every required core checkbox is proven, not merely
described. - A clean clone can start, seed, test, and demonstrate the
end-to-end flow. - The public repository has all required files.

**Evidence** - Final acceptance checklist with commands/results and demo
path.

------------------------------------------------------------------------

## 8. Internship acceptance checklist

Use this as the final gate; update status and evidence links as work is
completed.

-   [ ] Dedicated public repository and clean Git history.
-   [ ] Required `README.md`, `capstone.yaml`, `EVIDENCE.md`,
    `BUILDLOG.md`, `.env.example`, and `.gitignore`.
-   [ ] Layered architecture: HTTP, business logic, and persistence
    separated.
-   [ ] PostgreSQL persistence and migrations.
-   [ ] Authenticated widget CRUD.
-   [ ] Tenant isolation for widgets, submissions, and analytics.
-   [ ] Embed snippet generated for each widget.
-   [ ] Public config endpoint returns only safe fields and correct
    cache headers.
-   [ ] Versioned widget JavaScript delivery.
-   [ ] Widget renders on a different origin.
-   [ ] CORS preflight works for intended public endpoints.
-   [ ] Boundary validation and clean errors for malformed/oversized
    payloads.
-   [ ] Valid submission stored against correct widget and workspace.
-   [ ] Rate limiting produces `429` under a burst.
-   [ ] Legitimate request succeeds after the burst test.
-   [ ] At least one spam control demonstrably blocks a submission.
-   [ ] Geo provider fallback A → B is proven.
-   [ ] Both geo providers down still allows storage.
-   [ ] Failing notification does not prevent successful storage.
-   [ ] At least one background job has retry and failure-alert
    behavior.
-   [ ] Idempotency is implemented and proven where it matters.
-   [ ] Secrets are not committed or logged.
-   [ ] Evidence includes real test output/transcripts, not claims
    alone.
-   [ ] README setup works on a clean machine.

------------------------------------------------------------------------

## 9. Post-internship product phases --- separate from the original goals

**Important:** everything in this section is an extension after the
internship core is accepted. These goals must not be mixed into the core
acceptance checklist or allowed to delay submission.

### Phase 9 --- Production deployment v1

**Goal:** deploy the modular monolith safely to a public URL.

**Work** - Choose one cloud provider and a low-cost/free-tier-compatible
architecture after checking current pricing and limits. - Build an
immutable Docker image. - Configure HTTPS, domain/DNS if available,
environment configuration, and secret storage. - Use a managed
PostgreSQL service or a documented persistent database setup appropriate
to the budget. - Separate development, staging, and production
configuration. - Add startup, liveness, and readiness checks. - Run
migrations as a controlled release step, not unpredictably on every
application replica. - Add database backups and perform a restore
drill. - Add a staging smoke test and a documented rollback procedure. -
Set resource limits and basic abuse/cost controls. - Publish an honest
demo/privacy/limitations page.

**Gate** - Public end-to-end flow works on the deployed service. - A
failed release can be rolled back. - Backup restoration is tested, not
merely enabled. - No secrets are stored in source control.

### Phase 10 --- CI/CD and software supply-chain hygiene

**Goal:** make changes repeatable and safer to release.

**Work** - CI on pull requests: format, lint, type checks where
practical, unit/integration tests, migration checks, and build. - Build
and tag immutable images. - Dependency and container vulnerability
scanning. - Secret scanning. - Deploy to staging automatically; require
a deliberate production promotion. - Run post-deployment smoke tests. -
Document rollback and failed-deployment handling. - Generate a software
bill of materials if practical.

**Gate** - A pull request cannot merge if critical checks fail. - A
tagged build can be traced to a commit. - A deployment failure is
visible and recovery is documented.

### Phase 11 --- Redis and distributed rate limiting

**Goal:** make abuse controls consistent across multiple API instances.

**Work** - Introduce Redis only when there is a real
multi-instance/shared-state requirement. - Move rate-limit counters to
Redis with expiry and atomic operations. - Add shared caching only where
measurement shows a benefit. - Define Redis outage behavior: safe
fallback, bounded degradation, and alerts. - Keep PostgreSQL as the
source of truth for business data. - Test behavior with multiple API
instances and Redis unavailable.

**Gate** - Rate limits remain consistent across replicas. - Redis
failures do not accidentally disable all protections silently. - Cache
invalidation and TTL behavior are documented and tested.

### Phase 12 --- Durable queue, outbox, and worker separation

**Goal:** reliably process email, webhook delivery, and other slow tasks
independently from HTTP requests.

**Work** - Choose a queue appropriate to scale and cloud target. - Add a
transactional outbox or another explicitly justified reliable-publish
pattern so database commit and job publication cannot silently
diverge. - Separate API and worker runtime processes. - Add retry policy
with exponential backoff and jitter. - Add dead-letter handling, replay
tooling, and delivery attempt history. - Use idempotent consumers and
stable event IDs. - Add per-destination timeout and concurrency
controls. - Add webhook signatures, timestamp/replay protection, secret
rotation, and clear retry semantics. - Never retry indefinitely; define
retention and manual recovery.

**Gate** - Worker restart does not lose committed work. - Duplicate job
delivery does not duplicate external side effects where the provider
supports idempotency. - Failed jobs reach a visible terminal state and
can be safely inspected/replayed.

### Phase 13 --- Observability and operational readiness

**Goal:** know whether the service is healthy and diagnose failures
without exposing customer data.

**Work** - Structured JSON logs with request ID, route, status,
duration, and tenant-safe identifiers. - Metrics for request rate,
latency, error rate, `429`s, database pool usage, queue depth, job age,
retry count, and upstream failure rate. - Distributed tracing across
API, database, queue, and workers where feasible. - Dashboards and
actionable alerts with thresholds based on observed behavior. - Define
service-level indicators and an initial service-level objective. - Add
an incident runbook for database outage, queue backlog, provider outage,
abuse spike, and failed deploy. - Redact tokens, credentials, form
values, email addresses, and raw IPs from logs. - Add correlation IDs to
user-visible errors without leaking internals.

**Gate** - Simulated upstream failure and queue backlog are visible in
dashboards/alerts. - An operator can trace a request/job using a
correlation ID. - Alerts are actionable and have runbook links.

### Phase 14 --- Security, privacy, and customer trust

**Goal:** improve the service for real users and real submitted data.

**Work** - Add workspace export and deletion workflows. - Define
retention windows and a deletion policy for submissions, logs, backups,
and derived data. - Add a privacy notice and clear widget owner
responsibilities. - Add workspace roles and least-privilege
permissions. - Add audit events for security-sensitive owner actions. -
Review authentication/session expiry, password/token storage, CSRF risks
if cookie auth is used, CORS, SSRF, injection, rate limiting, and
dependency risks. - Protect webhook destination configuration against
SSRF: block private/link-local/metadata IP ranges, revalidate
redirects/DNS as appropriate, and restrict protocols/ports. - Add
security headers where applicable, request limits, and dependency update
policy. - Define key rotation and incident response procedures. -
Conduct a threat-model review before inviting external users.

**Gate** - Cross-tenant authorization tests cover all owner endpoints. -
Export/deletion behavior is documented and tested. - Webhook
destinations cannot reach prohibited internal resources. - Privacy and
security limitations are transparent.

### Phase 15 --- Product usability and integration improvements

**Goal:** make the service useful beyond a technical demo.

**Possible features** - Workspace onboarding and setup wizard. -
Multiple widget templates: contact, feedback, signup, and simple CTA. -
Configurable allowed origins, with clear guidance about what origin
checks do and do not secure. - Custom success/error messages and
accessibility improvements. - Email notification configuration and
delivery status. - Signed webhooks with delivery history and manual
retry. - CSV export with safe pagination and export limits. -
Search/filtering and saved views for submissions. - Data retention
controls per workspace. - Documentation, SDK/helper examples, and a
public status page. - Workspace-level usage quotas and abuse limits. -
Basic audit log and role-based membership.

**Gate** - Each new feature solves a user-validated problem, has
acceptance criteria, and does not weaken the core security model.

### Phase 16 --- Infrastructure as Code and cloud architecture

**Goal:** make infrastructure reproducible and deepen cloud engineering
skills.

**Work** - Select one provider (AWS, Azure, or GCP) based on learning
goals and budget. - Use Terraform or an equivalent IaC tool to define
networking, application runtime, database, secrets, logging, DNS, and
ingress/load balancing. - Separate reusable modules from environment
configuration. - Use least-privilege IAM/workload identity; avoid
long-lived cloud credentials where possible. - Define state
storage/locking securely. - Add plan review and controlled apply
workflow. - Document network boundaries, private/public resources,
egress, database access, and secret flow. - Add budget alerts and
resource cleanup procedures.

**Gate** - A new environment can be recreated from versioned
configuration. - No secret is stored in Terraform state/configuration in
plaintext by design. - Network and IAM decisions are documented and
reviewable.

### Phase 17 --- Scale, reliability, and performance

**Goal:** measure bottlenecks before adding complexity.

**Work** - Establish baseline load tests for widget config and
submission endpoints. - Profile slow queries and add indexes based on
evidence. - Test connection pool limits, concurrency, worker throughput,
and queue backlog. - Add load balancing and multiple API instances when
needed. - Define capacity assumptions and backpressure behavior. - Add
graceful shutdown and worker drain behavior. - Test database
failover/restore and queue outage scenarios. - Add CDN delivery for
immutable widget assets when justified. - Consider read replicas or
partitioning only after measurement indicates a need. - Write a
lightweight capacity and cost model.

**Gate** - A documented load test has reproducible parameters and
results. - The system has explicit overload behavior instead of
unbounded resource consumption. - Performance changes are backed by
measurements.

### Phase 18 --- Container orchestration (optional, only when justified)

**Goal:** learn orchestration from an application with real operational
needs.

**Work** - First deploy using a managed container service if it meets
needs. - Consider Kubernetes only after understanding container
networking, health checks, secrets, scaling, ingress, and deployment
rollbacks. - If using Kubernetes, define deployments, services, ingress,
probes, resource requests/limits, secrets integration, autoscaling, and
rollout strategy. - Keep database and queue managed where practical
rather than self-hosting everything for a portfolio demo. - Document
operational overhead and why orchestration is justified.

**Gate** - The orchestrated deployment improves a stated operational
requirement. - Rollout, failure recovery, scaling, and debugging are
demonstrated. - Kubernetes is not included solely as a résumé keyword.

### Phase 19 --- Optional advanced product and platform features

Pick only features supported by user needs and time:

-   Double opt-in and consent records.
-   Configurable targeting rules and display frequency.
-   Real-time dashboard updates via SSE/WebSockets.
-   CAPTCHA or risk-based bot defense with measured effectiveness.
-   Custom domains or white-labeling.
-   Usage metering and quota plans.
-   Billing integration in test mode first.
-   Multi-region architecture and disaster-recovery planning.
-   Analytics exports or event integrations.
-   Formal SLOs, error budgets, and incident exercises.

Each feature needs a separate design note, privacy/security review,
acceptance criteria, cost estimate, and rollback plan.

------------------------------------------------------------------------

## 10. Non-functional requirements

Use these as design targets; choose concrete numeric thresholds in the
design document based on expected traffic and hosting budget.

### Security

-   Authentication on owner routes.
-   Authorization and tenant scoping enforced server-side on every
    access.
-   Boundary validation and request-size limits.
-   Safe SQL/data access practices and database constraints.
-   Rate limiting and spam controls on public endpoints.
-   Secrets kept out of Git, logs, errors, and public config.
-   Strict CORS policy based on endpoint purpose.
-   External requests use timeouts and validated responses.
-   Webhook destination protections before accepting arbitrary URLs.
-   Security-sensitive actions logged without sensitive payloads.

### Reliability

-   Optional providers cannot make submission storage fail.
-   Secondary actions cannot undo a successful submission.
-   Retries are bounded, observable, and safe.
-   Background work has persistent state, retry behavior, and a failure
    signal.
-   Database migrations and backup restoration are tested.
-   Shutdown behavior does not silently abandon work.

### Performance and resource controls

-   Request body, field count, field length, page size, and query range
    limits.
-   Database indexes for expected query patterns.
-   HTTP caching for versioned assets and public config.
-   Timeouts and concurrency limits for upstream services.
-   Load testing before claiming production scale.
-   Cost/budget alerts before sustained public use.

### Privacy

-   Collect only configured fields.
-   Keep raw IP retention minimal and documented.
-   Avoid raw submissions in logs.
-   Document data retention, deletion, export, and backup implications.
-   Do not use real people's personal data for demos; use synthetic seed
    data.
-   Obtain appropriate consent and legal review before using this for
    regulated or sensitive data.

### Operability

-   Health/readiness endpoints.
-   Structured logs and request IDs.
-   Reproducible startup, migration, seed, test, and deployment
    commands.
-   Runbooks for common failures.
-   Alerts for persistent worker/upstream failures after deployment.
-   A clear status/limitations page for public demos.

------------------------------------------------------------------------

## 11. Testing strategy

Testing is not a final phase only. Add tests alongside every feature.

### Unit tests

-   Schema validation and limits.
-   Widget configuration rules.
-   Tenant authorization decisions.
-   Idempotency key/fingerprint rules.
-   Geo fallback decision logic.
-   Notification retry decisions.
-   Analytics aggregation logic.

### Integration tests

-   API + PostgreSQL.
-   Migrations from a clean database.
-   Authentication and tenant isolation.
-   Public config and cache headers.
-   CORS/preflight behavior.
-   Submission storage.
-   Background job persistence and retries.
-   Webhook signature verification if implemented.

### Security and abuse tests

-   Missing/invalid credentials.
-   Tenant A attempting tenant B's resources.
-   Unknown fields, malformed JSON, oversized bodies.
-   Burst requests and rate-limit recovery.
-   Honeypot submissions.
-   Untrusted forwarded IP headers.
-   Public config leaking private fields.
-   SSRF attempts against webhook URLs in later phases.
-   Secret and personal-data leakage in logs.

### Failure-injection tests

-   Geo provider A down.
-   Geo provider B down.
-   Both geo providers down.
-   Email/webhook raises an exception.
-   Database unavailable.
-   Worker terminates mid-job.
-   Duplicate job delivery.
-   Redis unavailable (later).
-   Queue unavailable/backlogged (later).

### End-to-end acceptance test

A clean demo path should be: 1. Start services and apply migrations. 2.
Seed or create a workspace/user. 3. Authenticate and create a widget. 4.
Obtain the embed snippet. 5. Open the separate-origin HTML test page. 6.
Submit a valid form. 7. Confirm the submission is stored and visible to
the owner. 8. Run invalid, oversized, spam, rate-limit, fallback, and
notification-failure checks. 9. Confirm a different tenant cannot view
the data.

------------------------------------------------------------------------

## 12. Documentation system --- make future "truth docs" easy

The plan is the roadmap; it must not become the only source of truth.
Keep these documents short, factual, and updated when implementation
changes.

### Suggested repository structure

``` text
.
├── README.md
├── PLAN.md
├── BUILDLOG.md
├── EVIDENCE.md
├── capstone.yaml
├── .env.example
├── pyproject.toml
├── docker-compose.yml
├── alembic.ini
├── migrations/
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── repositories/
│   ├── schemas/
│   ├── services/
│   ├── jobs/
│   └── main.py
├── widget/
│   ├── src/
│   └── dist/
├── demo-site/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── e2e/
└── docs/
    ├── design.md
    ├── architecture/
    │   ├── overview.md
    │   ├── data-model.md
    │   ├── request-flows.md
    │   └── deployment.md
    ├── api/
    │   └── conventions.md
    ├── security/
    │   ├── threat-model.md
    │   └── privacy-and-retention.md
    ├── operations/
    │   ├── runbook.md
    │   ├── backup-restore.md
    │   └── incident-response.md
    ├── decisions/
    │   └── ADR-0001-modular-monolith.md
    └── truth/
        ├── system-map.md
        ├── environment-variables.md
        ├── background-jobs.md
        ├── caching-and-rate-limits.md
        └── known-limitations.md
```

Do not create every file as empty boilerplate on day one. Create each
document when its phase makes it useful.

### What each document should answer

-   **`README.md`:** What does this do? How do I run it? How do I
    seed/test/demo it? What are the limitations?
-   **`PLAN.md`:** What are we trying to build, in what order, and what
    is core versus future?
-   **`docs/design.md`:** Who has the problem, what is the scope, and
    what is explicitly not being built?
-   **`docs/architecture/overview.md`:** What are the runtime components
    and how do they connect?
-   **`docs/architecture/data-model.md`:** What data exists, who owns
    it, what constraints/indexes apply, and what is retained/deleted?
-   **`docs/architecture/request-flows.md`:** What happens step by step
    for owner CRUD, widget load, submission, and background processing?
-   **`docs/api/`:** What endpoints exist, who can call them, and what
    are the request/response/error contracts?
-   **`docs/security/threat-model.md`:** What can go wrong, what
    protects against it, and which risks remain?
-   **`docs/security/privacy-and-retention.md`:** What personal data is
    collected, why, for how long, and how can it be exported/deleted?
-   **`docs/operations/runbook.md`:** What to check when a service,
    provider, worker, or queue fails?
-   **`docs/operations/backup-restore.md`:** How are backups made and
    how is restoration verified?
-   **`docs/decisions/ADR-*.md`:** Why was a significant technology or
    design selected? What alternatives were considered?
-   **`docs/truth/system-map.md`:** What exists in code today, with
    paths to the implementation and tests?
-   **`docs/truth/environment-variables.md`:** Which environment
    variables exist, what they mean, whether they are secret, and where
    they are used?
-   **`docs/truth/background-jobs.md`:** Which jobs exist, triggers,
    retry policy, idempotency, and failure behavior?
-   **`docs/truth/caching-and-rate-limits.md`:** What is cached, TTLs,
    cache invalidation, rate-limit keys, storage, and outage behavior?
-   **`docs/truth/known-limitations.md`:** What is incomplete, what is
    unsafe for production, and what assumptions remain?
-   **`EVIDENCE.md`:** What concrete output proves each requirement?
-   **`BUILDLOG.md`:** What was tried, what AI helped with, what was
    wrong, and what was changed?

### Truth-document rule

A truth document describes **what the current code actually does**, not
what the plan hopes it will do. Every major claim should link to code,
configuration, tests, or a runbook. Update truth docs in the same pull
request as behavior changes. If implementation and docs disagree, fix
one before merging.

------------------------------------------------------------------------

## 13. Definition of done for every phase

A phase is complete only when all of the following are true:

1.  Its stated gate is satisfied.
2.  Tests cover normal behavior and at least the important failure case.
3.  The application still starts from a clean checkout.
4.  No secrets or personal data were added to logs/repository.
5.  Migrations are included for schema changes.
6.  `README.md`, `EVIDENCE.md`, and relevant truth docs are updated.
7.  Any major design trade-off is captured in an ADR.
8.  The work is committed in small, meaningful commits.
9.  Remaining limitations are written down rather than hidden.

------------------------------------------------------------------------

## 14. Risks and guardrails

  -----------------------------------------------------------------------
  Risk                                Guardrail
  ----------------------------------- -----------------------------------
  Scope creep delays the internship   Core acceptance checklist is the
                                      priority; later phases are
                                      explicitly separate

  Cross-tenant data leak              Centralize workspace scoping, add
                                      negative authorization tests,
                                      review every owner query

  Public endpoint abuse               Request limits, rate limits,
                                      honeypot, timeouts, payload bounds,
                                      monitoring

  External service failure            Provider fallback, bounded
                                      timeouts, graceful degradation,
                                      deterministic tests

  Duplicate submissions or            Defined idempotency keys, stable
  notifications                       event IDs, database uniqueness,
                                      idempotent worker behavior

  Data loss during background work    Persistent jobs/outbox where
                                      needed, retries, failure state,
                                      backup/restore testing

  Sensitive data in logs              Structured redaction, no raw
                                      payload logging, tests for log
                                      output

  Deployment becomes expensive        Budget limits, resource caps, usage
                                      alerts, cleanup instructions

  Premature microservices/Kubernetes  Modular monolith first; split only
                                      when evidence justifies it

  Documentation drifts from code      Truth-doc updates are part of each
                                      phase's definition of done
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 15. Immediate next actions

Do these in order; do not start cloud deployment or Kubernetes work yet.

1.  Create the dedicated public repository and initial required files.
2.  Commit this plan as `PLAN.md`.
3.  Write `docs/design.md` using the product vision, users, core scope,
    data model, API surface, and non-goal in this plan.
4.  Write `docs/architecture/data-model.md` and
    `docs/security/threat-model.md`.
5.  Choose and document the initial authentication approach, database
    access pattern, and persistent background-job approach.
6.  Create the FastAPI/PostgreSQL/Docker walking skeleton with
    migrations and a test command.
7.  Start Phase 2 only after the design decisions are recorded.
8.  Work phase by phase, keeping the core acceptance checklist green
    before adding stretch goals.

------------------------------------------------------------------------

## 16. Decision log starter

Record the actual decision and rationale before implementation; replace
the prompts below rather than leaving them unresolved indefinitely.

-   [ ] Authentication approach: `TBD`
-   [ ] ORM/data-access approach: `TBD`
-   [ ] Initial background-job mechanism satisfying retries and failure
    alerts: `TBD`
-   [ ] Idempotency key format, scope, retention, and conflict behavior:
    `TBD`
-   [ ] CORS allowlist strategy for local and deployed environments:
    `TBD`
-   [ ] Geo provider timeout/retry limits: `TBD`
-   [ ] Submission/IP retention policy: `TBD`
-   [ ] Notification delivery semantics and retry policy: `TBD`
-   [ ] Deployment provider and budget constraints (post-internship):
    `TBD`

**Final guiding principle:** finish a small, correct, well-tested core
first. Then make it observable, deployable, secure, and scalable in
deliberate steps. The project should demonstrate not just that you can
build a backend, but that you can explain its behavior, prove its
guarantees, and operate it responsibly.
