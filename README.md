# Lead-Capture Platform

A configurable lead-capture platform with an embeddable website widget. This project is being developed as part of the FlyRank Backend Engineering Internship.

> **Project status:** In development. This README is a starting point and will be updated as features are implemented.

## Overview

The platform is intended to let users create and manage lead-capture widgets, embed them on external websites, collect submissions, and review captured leads.

## Planned Features

- [ ] User authentication and workspace management
- [ ] Create, view, update, and manage widgets
- [ ] Embeddable JavaScript widget
- [ ] Public widget configuration and lead-submission APIs
- [ ] Store and review lead submissions
- [ ] Input validation and consistent API errors
- [ ] Tenant isolation and security controls
- [ ] Geolocation enrichment with provider fallback
- [ ] Optional email notifications and webhook delivery
- [ ] Background jobs with retries and failure visibility
- [ ] Analytics and summary endpoints
- [ ] Automated tests and deployment setup

These are planned capabilities, not a claim that they are already implemented. Update the checklist as the project progresses.

## Tech Stack

The intended starting stack is:

- **Language:** Python
- **API framework:** FastAPI
- **Database:** PostgreSQL
- **ORM and migrations:** SQLAlchemy and Alembic
- **Local development:** Docker / Docker Compose
- **Testing:** pytest and HTTPX
- **Widget:** JavaScript

The actual dependencies and versions should be recorded here after the initial project setup is in place.

## Project Structure

The structure below is illustrative and will be adjusted to match the actual repository as it develops.

```text
lead-capture-platform/
├── AGENTS.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── domain_models.md
│   ├── database_schema.md
│   ├── api_contracts.md
│   ├── widget_contract.md
│   ├── submission_flow.md
│   ├── security_spec.md
│   └── event_spec.md
├── app/                  # Application code (planned)
├── tests/                # Automated tests (planned)
├── migrations/           # Database migrations (planned)
├── docker-compose.yml     # Local services (planned)
├── Dockerfile             # Application image (planned)
├── .env.example           # Example configuration (planned)
└── pyproject.toml         # Python project configuration (planned)
```

## Getting Started

Setup instructions will be added once the application scaffold and local development workflow are implemented.

### Prerequisites

To be confirmed based on the initial setup. The intended tools include Python, Docker, and PostgreSQL.

### Installation

_To be added._

### Configuration

Configuration will be managed through environment variables or the project's settings system. An `.env.example` file should document required variable names without containing real credentials.

_To be added after configuration is implemented._

### Run Locally

_To be added after the application entry point and development commands are established._

## Development Workflow

1. Read `AGENTS.md` before making code changes.
2. Review the relevant technical documents in `docs/`.
3. Inspect the current implementation before assuming a feature exists.
4. Make one focused change at a time.
5. Add or update tests for changed behavior.
6. Run the relevant tests and checks.
7. Update this README and technical documentation when implementation details change.

## Documentation

The `docs/` directory contains the evolving technical design for the project.

| Document | Purpose |
|---|---|
| `architecture.md` | System components and their interactions |
| `domain_models.md` | Core entities, relationships, and business rules |
| `database_schema.md` | Proposed database tables, constraints, and indexes |
| `api_contracts.md` | API endpoints, requests, responses, and errors |
| `widget_contract.md` | Embedding, widget configuration, and browser-to-API behavior |
| `submission_flow.md` | Lead submission lifecycle and failure handling |
| `security_spec.md` | Security boundaries and expected controls |
| `event_spec.md` | Background job payloads, retries, and recovery behavior |

Documentation may describe proposed behavior until the corresponding implementation is completed. Keep it synchronized with the actual code.

## Testing

_Test commands and coverage expectations will be added after the test setup is implemented._

## Configuration and Secrets

- Never commit real API keys, passwords, tokens, or production credentials.
- Keep `.env` files containing local secrets out of version control.
- Maintain `.env.example` with placeholder values for required settings.
- Validate configuration at application startup where appropriate.

## Roadmap

The implementation roadmap will be maintained as the project evolves.

- [ ] Initialize the application and development environment
- [ ] Implement the first API slice
- [ ] Add database persistence and migrations
- [ ] Implement widget management and public submission
- [ ] Add validation, security, and reliability controls
- [ ] Add asynchronous processing and integrations
- [ ] Add analytics, deployment, and operational checks

Reorder or refine these items as implementation priorities become clearer.

## License

_To be decided._
