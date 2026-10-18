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
│   ├── event_spec.md
│   └── decisions/            # Architecture decision records
├── app/                      # Application code
├── tests/                    # Automated tests
├── migrations/               # Database migrations
├── scripts/                  # Utility scripts (seed, worker)
├── docker-compose.yml        # Local services
├── Dockerfile                # Application image
├── .env.example              # Example configuration
└── pyproject.toml            # Python project configuration
```

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for PostgreSQL)
- Git

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd lead-capture-platform

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your settings (at minimum DATABASE_URL and SECRET_KEY)
```

### Configuration

Configuration is managed through environment variables. Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Required variables:
- `DATABASE_URL` — PostgreSQL connection string (e.g., `postgresql+asyncpg://postgres:postgres@localhost:5432/leadcapture`)
- `SECRET_KEY` — JWT signing secret (generate with `openssl rand -hex 32`)
- `JWT_ALGORITHM` — Default `HS256`
- `JWT_EXPIRE_MINUTES` — Default `30`

See `.env.example` for all available options.

### Run Locally (Development)

**Option 1: With Docker Compose (recommended — includes PostgreSQL)**

```bash
# Start PostgreSQL
docker compose up -d

# Run database migrations
alembic upgrade head

# Seed demo data (optional)
python scripts/seed.py

# Start the API server
uvicorn app.main:app --reload --port 8000
```

**Option 2: Without Docker (if you have PostgreSQL running locally)**

```bash
# Ensure PostgreSQL is running and DATABASE_URL in .env points to it
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health/live`

### Run Tests

```bash
# Unit tests (no database required)
python -m pytest tests/ -v

# Integration tests (requires running PostgreSQL)
docker compose up -d
alembic upgrade head
python -m pytest tests/ -v
```

### Demo Widget

Start a simple HTTP server for the demo page on a different port to test cross-origin behavior:

```bash
# Terminal 1: API server
uvicorn app.main:app --reload --port 8000

# Terminal 2: Demo page (different origin)
cd demo
python -m http.server 3000
```

Open `http://localhost:3000` in your browser to test the widget.

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
| `decisions/` | Architecture decision records (ADRs) |

Documentation may describe proposed behavior until the corresponding implementation is completed. Keep it synchronized with the actual code.

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=term-missing

# Run only unit tests (fast, no DB)
python -m pytest tests/ -k "not integration" -v

# Run integration tests (requires DB)
python -m pytest tests/ -k "integration" -v
```

Code quality checks:
```bash
# Linting
ruff check .

# Type checking
mypy app/
```

## Configuration and Secrets

- Never commit real API keys, passwords, tokens, or production credentials.
- Keep `.env` files containing local secrets out of version control.
- Maintain `.env.example` with placeholder values for required settings.
- Validate configuration at application startup where appropriate.

## Roadmap

The implementation roadmap will be maintained as the project evolves.

- [x] Initialize the application and development environment (Phase 0)
- [x] Design decisions and documentation alignment (Phase 1)
- [ ] Add database persistence and migrations (Phase 2)
- [ ] Implement widget management and public submission (Phases 3-5)
- [ ] Add validation, security, and reliability controls (Phases 3-6)
- [ ] Add asynchronous processing and integrations (Phase 6)
- [ ] Add analytics, deployment, and operational checks (Phases 7-8)

Reorder or refine these items as implementation priorities become clearer.

## License

_To be decided._