# Agent Working Rules

**Project:** Lead-Capture Platform  
**Purpose:** Make coding agents work deliberately, inspect the existing project before acting, follow a step-by-step workflow, and avoid unrelated or speculative changes.

These rules apply to coding agents, AI assistants, and automated contributors working in this repository. Treat them as project instructions, not optional suggestions.

## 1. Core principles

1. **Inspect before changing.** Never assume the repository structure, framework, implementation status, or current branch. Look at the actual files first.
2. **Plan before editing.** Understand the task, identify the smallest useful change, list the files likely to be affected, and decide how it will be verified.
3. **Follow the existing implementation.** Prefer established project patterns over introducing a new architecture or dependency.
4. **Work in small steps.** Make one coherent change at a time. Verify it before moving to the next step.
5. **Do only the requested work.** Do not add unrelated features, refactor neighboring code, rename things, or rewrite whole files without a clear reason.
6. **Do not invent project facts.** If a behavior, requirement, or implementation detail is unknown, inspect the repository. If it remains unclear, state the uncertainty or ask a focused question.
7. **Verify before claiming success.** Run relevant tests and checks when possible. Clearly report anything not run and why.
8. **Protect existing work.** Do not overwrite, discard, or reformat unrelated user changes.

## 2. Mandatory workflow

Follow these steps for every non-trivial task, in order.

### Step 1 — Read project instructions

- Find and read the root `AGENTS.md`, if present.
- Read applicable nested `AGENTS.md` files for the directories being changed.
- Read the relevant `README.md`, setup instructions, and nearby documentation.
- Check repository status before editing so existing changes are not mistaken for agent changes.
- Treat explicit user instructions in the current task as requirements, subject to higher-priority safety and platform rules.

Do not skip instructions because the task looks small.

### Step 2 — Inspect the repository

Before proposing code changes, inspect the actual structure and relevant implementation.

Look for:
- Application entry points and route registration.
- Existing API routes, schemas, services, models, and repositories.
- Database configuration, migrations, and transaction boundaries.
- Authentication, authorization, and tenant/workspace checks.
- Existing tests, fixtures, and test conventions.
- Configuration and environment variable examples.
- Dependency manifests, lockfiles, Docker files, and CI configuration.
- Relevant documentation in `docs/`.

Use targeted file searches and read the relevant files. Do not dump or read the entire repository if a focused inspection is enough.

**Never assume a file exists because it appears in a plan or documentation.** Confirm it on disk.

### Step 3 — Establish the current state

Summarize internally, or briefly to the user when useful:
- What currently exists.
- What is missing or broken.
- Which existing behavior must remain unchanged.
- Which requirements apply to this task.
- Any blockers, ambiguity, or important risks.

Distinguish clearly between:
- **Implemented:** confirmed in code and tests.
- **Documented/planned:** present only in documentation or plans.
- **Unknown:** not yet verified.

Documentation does not prove that a feature exists in code.

### Step 4 — Define the smallest plan

Before editing, create a short ordered plan. A typical plan is:

1. Inspect the relevant implementation and tests.
2. Identify the exact behavior or defect to address.
3. Make the smallest compatible code change.
4. Add or update tests for the behavior.
5. Run focused tests and relevant quality checks.
6. Review the diff and report the outcome.

For a task that changes multiple layers, list the layers and their dependencies in order. Do not start broad implementation until the plan is coherent.

If a missing requirement materially changes the design, ask one focused clarifying question instead of guessing. Otherwise, make a conservative assumption, state it when useful, and proceed.

### Step 5 — Implement incrementally

- Make the smallest coherent change that satisfies the task.
- Follow existing naming, formatting, typing, error-handling, and dependency-injection conventions.
- Keep route handlers thin; place business rules in the project's established service/domain layer.
- Keep database access in the established persistence layer where one exists.
- Reuse existing utilities and dependencies when suitable.
- Avoid adding dependencies unless the requirement cannot reasonably be met with the current stack.
- Do not introduce a new framework, architecture, queue, cache, or abstraction merely because it is familiar or fashionable.
- Avoid unrelated cleanup and speculative future-proofing.
- Do not silently change API contracts, database semantics, authentication behavior, or public widget behavior.
- Do not weaken validation, authorization, rate limits, or security controls to make tests pass.
- Do not hard-code secrets, credentials, environment-specific URLs, or private data.
- Do not edit generated files manually when they should be regenerated from their source.

When the change spans several files, implement in dependency order—for example, schema/model, migration, service logic, route integration, then tests and documentation—adjusting to the repository's actual architecture.

### Step 6 — Test the change

Choose checks based on the change. Prefer focused checks first, then broader checks when appropriate.

Examples:
- Run the relevant unit or integration tests.
- Add regression tests for reported bugs.
- Test validation and error cases, not only the happy path.
- For API changes, verify status codes, response shape, and authorization behavior.
- For database changes, verify migrations and transaction/constraint behavior.
- For tenant-scoped operations, verify cross-workspace access is rejected.
- For asynchronous work, verify retries, duplicate delivery, and terminal failure handling where relevant.
- Run formatting, linting, type checks, or the project's equivalent if configured.

If a check cannot run because a service, dependency, secret, or environment is unavailable, report that explicitly. Do not claim it passed.

Do not modify or delete tests merely to make a failing test suite green unless the test itself is demonstrably incorrect and the change is justified.

### Step 7 — Review the diff

Before finishing:

- Inspect every changed file and the final diff.
- Check for unrelated edits, accidental deletions, debug prints, TODOs added without need, and secrets.
- Check that error handling and return values are correct.
- Check that new code matches existing patterns.
- Check whether documentation or examples need updating.
- Check that migrations and configuration changes are included when required.
- Confirm no user changes were overwritten.

If the diff is larger than the task requires, reduce it.

### Step 8 — Report completion

Give a concise, factual report containing:

1. **What changed:** the behavior and main files affected.
2. **Why:** how the change addresses the request.
3. **Verification:** exact tests/checks run and their results.
4. **Limitations:** checks not run, assumptions, or remaining work.
5. **Next step:** only if a concrete dependency remains.

Never say “everything works” based only on code inspection. Never say tests passed unless they were actually run and passed.

## 3. Task sizing and approval boundaries

### Small, clear tasks

Examples: correcting a typo, adding a focused test, fixing a narrow bug.

- Inspect the relevant files.
- Make the change.
- Run the narrowest useful check.
- Review and report.

Do not create a long planning ceremony for a trivial edit, but do not skip inspection.

### Medium or multi-file tasks

Examples: adding an endpoint, introducing a database model, changing widget submission behavior.

- Inspect routes, services, models, migrations, tests, and docs relevant to the feature.
- Present or establish a short implementation plan.
- Implement in dependency order.
- Test each important boundary.
- Review the final diff.

### Large, ambiguous, or architecture-changing tasks

Examples: introducing a queue, changing authentication, restructuring persistence, changing the public widget contract.

- Inspect the relevant system end-to-end.
- Identify decisions, tradeoffs, and compatibility risks.
- Separate required work from optional improvements.
- Ask for confirmation before a major irreversible or scope-expanding decision when user intent is unclear.
- Prefer a small proof of concept before broad implementation.
- Update architecture and technical documentation only after the design is understood.

Do not interpret “be proactive” as permission to make large, unrelated, or irreversible changes.

## 4. Project-specific engineering rules

These rules reflect the intended Lead-Capture Platform design. Verify the actual implementation before applying them, and update the code/docs together when decisions change.

### 4.1 Architecture and scope

- Prefer the existing FastAPI modular-monolith structure unless the repository explicitly adopts another design.
- Keep HTTP concerns, business logic, persistence, and external integrations separated according to the established project pattern.
- Keep the internship core separate from optional post-internship expansion.
- Do not introduce microservices or distributed infrastructure without a clear requirement.
- Treat `docs/` as design guidance; actual code, migrations, tests, and the agreed requirements determine what is implemented.

### 4.2 API and compatibility

- Follow the existing API versioning and response conventions.
- Validate request bodies, query parameters, path parameters, and configuration.
- Return consistent JSON errors without leaking internal exception details.
- Preserve documented API behavior unless the task explicitly changes it.
- Update API documentation and tests when a contract changes.
- Treat public widget configuration and submission endpoints as untrusted public interfaces.

### 4.3 Tenant isolation and security

- Enforce workspace/tenant ownership on every protected resource access.
- Never trust a workspace ID supplied by the client without checking authorization.
- Treat public widget identifiers as identifiers, not credentials.
- Apply validation, rate limiting, origin/CORS rules, and payload-size limits where required.
- Avoid logging lead contents, secrets, tokens, full IP addresses, or webhook credentials.
- Protect outbound webhook/provider calls against SSRF and unsafe redirects.
- Never weaken security controls just to make local development easier.

### 4.4 Lead submission reliability

- A lead is considered captured only after its database transaction commits successfully.
- Do not return a success response before the durable submission write succeeds.
- Failures in optional geolocation, email, or webhook work must not invalidate a committed lead.
- Use the repository's chosen durable background-job/outbox design if implemented.
- Do not describe in-process background tasks as durable across process restarts.
- Make retries bounded and handlers idempotent where practical.
- Preserve stable identifiers for idempotency and webhook delivery.

### 4.5 Database changes

- Use the project's migration system; do not rely on manually changing a local database.
- Include constraints and indexes that support the intended invariants and query patterns.
- Check delete behavior, uniqueness, nullability, and tenant integrity.
- Keep schema migrations reversible when the migration framework and change permit it.
- Do not rewrite or squash existing migrations without explicit need and awareness of deployment consequences.
- Test transaction boundaries and failure paths for critical writes.

### 4.6 External services and configuration

- Read configuration from the project's established settings mechanism.
- Update `.env.example` or equivalent for new required configuration, but never put real secrets there.
- Give external calls explicit timeouts and classify retryable versus permanent failures.
- Handle provider failures without leaking sensitive response data.
- Do not add a new provider or integration unless it is part of the task or explicitly approved.

## 5. Documentation rules

Before changing documentation:

1. Inspect the relevant existing document and the code it describes.
2. Preserve existing terminology and structure where possible.
3. Mark proposals as proposed/planned if they are not implemented.
4. Update only the sections affected by the change.
5. Keep examples consistent with the real API, schema, and configuration.
6. Do not claim that tests, security controls, migrations, jobs, or monitoring exist unless verified.

When code and documentation disagree, do not silently choose one. Determine the intended contract from requirements and current behavior, then update the appropriate side and note any breaking change.

## 6. Git and workspace safety

- Check `git status` before editing and before finalizing.
- Do not reset, clean, checkout over, or discard user changes.
- Do not rewrite shared history, force-push, commit, or push unless asked.
- Do not stage unrelated files.
- Do not create commits unless requested or required by the user's workflow.
- Avoid destructive database commands. Confirm the target environment before any reset or data deletion.
- Never print secrets from environment files or credentials during inspection.
- Do not install packages or run expensive commands without a reason; follow the repository's setup and lockfile conventions.

## 7. When to stop and ask

Pause and ask a focused question when:

- Two plausible interpretations would lead to materially different behavior.
- A requirement conflicts with an existing public contract or security boundary.
- A task requires a destructive action or risks deleting user data.
- A major dependency, architecture, or paid external service is needed but not specified.
- The repository state is inconsistent and the safe path cannot be inferred.
- The task cannot be completed without credentials or access the agent does not have.

Do not ask about details that can be resolved safely by inspecting the repository or following an established convention. If the ambiguity is low-risk, state the assumption and proceed.

## 8. Definition of done

A task is complete only when all applicable items are satisfied:

- [ ] Relevant instructions and implementation were inspected.
- [ ] The change matches the requested scope.
- [ ] Existing conventions and security boundaries are preserved.
- [ ] Tests were added or updated when behavior changed.
- [ ] Relevant checks were run, with failures or omissions reported honestly.
- [ ] The final diff was reviewed for unrelated changes and sensitive data.
- [ ] Documentation/configuration was updated if needed.
- [ ] The final report states what changed, what was verified, and what remains.

## 9. Required response format for coding agents

For non-trivial tasks, report in this format:

```text
Plan
1. ...
2. ...
3. ...

Changes
- ...

Verification
- Command: ...
  Result: passed / failed / not run
- ...

Assumptions or blockers
- None / ...
```

Keep the plan short and specific. If implementation reveals that the plan must change, explain the reason before making a substantial scope change. The purpose of planning is to guide work—not to create paperwork or to pretend that unverified steps happened.
