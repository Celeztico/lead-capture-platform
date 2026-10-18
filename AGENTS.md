# AGENTS.md — Lead-Capture Platform

## 1. Purpose and priority

This file defines the working rules for any AI coding agent or automated assistant working in this repository. Follow these rules before making code, configuration, documentation, environment, or infrastructure changes.

**Highest-priority environment rule: do not install software or applications onto the user's physical/local system.** The user explicitly wants the current system left as-is. If a required application or runtime is missing from the current environment, report that fact and stop trying to install it. Do not work around this restriction by trying another package manager, installer, script, binary download, privileged command, or automatic setup process.

If a repository-specific instruction conflicts with this rule, the no-install rule takes precedence.

## 2. Mandatory no-install and environment-boundary policy

### 2.1 Never install missing applications

- Do **not** install, download for installation, enable, or configure a missing system application on the user's physical/local machine.
- Do not run installation commands such as `apt install`, `apt-get install`, `dnf install`, `yum install`, `pacman -S`, `brew install`, Windows package-manager installs, `curl | sh`, or equivalent commands.
- Do not use `sudo` or administrator privileges to install or enable software.
- Do not install Docker Engine/Desktop, Docker Compose, PostgreSQL, database servers, Redis, Node.js, system services, or other applications onto the physical/local system.
- Do not repeatedly retry an unavailable command or try alternate installation methods after discovering that the application is missing.
- Do not silently substitute a different runtime or infrastructure setup that changes the user's machine.
- Do not start a system-wide service or change system configuration merely to make a test pass.
- Do not assume that a package listed in a project file is installed. Check what is available before relying on it.

Python dependencies inside an already-existing project virtual environment may be installed only when that is already part of the project's established workflow and does not install or modify system applications. If unsure whether an action changes the host system, do not perform it; explain the concern and ask first.

### 2.2 Stop, report, and wait when a prerequisite is missing

When a required application or capability is unavailable:

1. Check whether it is already available using a non-destructive command (for example, `command -v docker`, `docker --version`, or checking an existing virtual environment).
2. If it is missing or unusable, **stop the affected task immediately**. Do not attempt to install it.
3. Tell the user:
   - which command/application is missing or unavailable;
   - which test or task cannot be completed in the current environment;
   - that no installation was attempted;
   - what needs to be run on the designated Linux server VM, or what confirmation/access is needed to continue.
4. Continue only with independent work that does not require the missing prerequisite and does not violate this policy. Clearly mark blocked checks as **NOT RUN / BLOCKED**, never as passed.
5. Do not keep retrying the blocked operation unless the user provides new information or explicitly authorizes a different approach. Even with such authorization, do not install onto the physical/local system unless the user explicitly changes the no-install policy.

Example: if Docker is not available locally, report that Docker-dependent tests are blocked and use the designated Linux server VM for them. Do not attempt to install Docker locally.

### 2.3 The Linux server VM is the environment for infrastructure-dependent work

The user has designated a Linux server virtual machine as the environment for infrastructure and testing that requires applications not present on the physical/local system.

- Docker and the PostgreSQL Docker deployment are on the designated Linux server VM. Run Docker-dependent workflows and tests that require the Docker/PostgreSQL services there.
- Any task requiring an application that is absent locally must be performed on the designated Linux server VM **if that application is available there and the required access is configured**.
- This includes, as applicable, Docker Compose orchestration, PostgreSQL integration tests, container builds, service-to-service networking tests, and other infrastructure-dependent validation.
- Do not claim to have run a command on the VM unless you actually have an authorized connection/tool and observed its result.
- If the VM is not accessible from the current session, stop the infrastructure-dependent task and provide the exact command(s) or steps for the user to run on the VM. Do not install the missing application locally as a fallback.
- Do not copy secrets, credentials, SSH private keys, production data, or other sensitive files to another environment. Use only approved access paths and existing environment configuration.
- Keep the physical/local system and the Linux server VM distinct. A tool being available on one does not mean it is available on the other.

### 2.4 Non-destructive environment checks

Before running tests or infrastructure commands, inspect the repository and check the relevant tool availability. Prefer read-only checks, for example:

```bash
command -v python
python --version
command -v pytest
command -v docker
docker --version
docker compose version
command -v psql
psql --version
```

Only run a version command after confirming the command exists, or handle its absence without retrying installation. Do not run every check blindly if it could trigger side effects.

## 3. Repository-first workflow

1. Inspect the repository structure and current Git status before changing files.
2. Read this `AGENTS.md`, the README, the project plan, and relevant documents before implementing a feature.
3. Inspect existing code, configuration, migrations, tests, and established conventions. Do not assume the repository is empty or that planned architecture is already implemented.
4. Identify which work can be done in the current environment and which work depends on the Linux server VM.
5. For non-trivial changes, state a short implementation plan and identify expected files and tests.
6. Make the smallest coherent change that satisfies the requirement. Avoid unrelated refactors, generated-file churn, or speculative dependencies.
7. Run only checks whose prerequisites are available. Report exact commands and results.
8. Review the diff for correctness, security, accidental changes, secrets, and scope before finishing.
9. Summarize what changed, what was tested, what was not run, and any remaining blockers.

Do not overwrite user changes or discard uncommitted work. Do not reset, clean, force-push, or perform destructive Git operations unless the user explicitly requests and confirms the specific action.

## 4. Project context and architecture

This project is a SaaS-style lead-capture platform with embeddable widgets. The intended stack includes Python, FastAPI, PostgreSQL, SQLAlchemy/Alembic, Docker Compose, pytest/HTTPX, and a browser-side JavaScript embed. Treat these as project goals, not proof that every dependency or service exists in every environment.

The system is expected to support:

- authenticated widget management and workspace/tenant isolation;
- public widget configuration and cross-origin form submissions;
- validation, safe JSON errors, request-size limits, rate limiting, and spam prevention;
- persistent submissions and dashboard queries/aggregates;
- geolocation provider fallback;
- optional email and webhook delivery with retries and failure handling;
- database migrations, indexes, idempotency, and environment-based secrets.

Read the current project documentation before changing any of these areas. Documentation may describe a target design; verify implementation in the code before claiming a feature exists.

## 5. Security and reliability rules

- Enforce workspace/tenant ownership in server-side queries and service logic; never rely only on client-supplied IDs.
- Keep secrets in environment configuration or approved secret storage. Never commit real credentials, tokens, private keys, or production data.
- Validate and bound public input, request body size, pagination, and external-service timeouts.
- Treat widget embed requests and public submission endpoints as untrusted.
- Avoid server-side request forgery (SSRF) in webhook or URL-fetching functionality; validate destinations and block unsafe internal targets.
- Keep core submission persistence independent from optional geolocation, email, and webhook failures where the design requires it.
- Use bounded retries, idempotency, and observable failure states for asynchronous work.
- Avoid logging personal data, secrets, full submitted form contents, or sensitive headers unnecessarily.
- Add or update tests for security boundaries and failure cases when implementing related behavior.

## 6. Dependencies and configuration

- Prefer existing dependencies and tools over adding new ones.
- Before proposing a new dependency, explain why it is necessary and check whether the current stack already provides the required capability.
- Do not add a dependency that requires a missing system application without clearly identifying that runtime prerequisite.
- Never make project setup scripts automatically install system applications.
- Keep `.env` files and secrets out of version control. Update example configuration with placeholders only.
- Do not change the expected database host or connection strategy merely to make the code run in the current environment. Follow the documented environment split and the user's configuration.

## 7. Testing policy

- Run fast, environment-independent tests locally when their prerequisites are available.
- Run tests that require Docker, PostgreSQL, containers, or other missing applications on the designated Linux server VM.
- Do not report a test as passing unless it was actually executed and passed.
- For every blocked check, record the reason, such as `BLOCKED: Docker is not installed in the current environment; run this check on the Linux server VM`.
- Distinguish unit tests, static checks, integration tests, and end-to-end tests in reports.
- Never install an application to turn a blocked test into a passing test.
- If a VM test cannot be executed because access is unavailable, provide the exact command and expected prerequisites for the user to run there.

## 8. Documentation and completion report

Keep documentation aligned with the implementation. Update the relevant technical document when a material contract, schema, security rule, event, or operational workflow changes.

At completion, report:

- **Changed:** files and behavior changed.
- **Tested:** exact commands run and their outcomes.
- **Blocked / not run:** checks requiring unavailable tools or VM access.
- **Environment actions:** explicitly confirm that no missing system application was installed.
- **Follow-up:** any VM command, user decision, or prerequisite still needed.

Never claim that an application was installed, a service was started, a migration ran, or a test passed unless the observed execution supports that statement.
