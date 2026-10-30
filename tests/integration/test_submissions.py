import json
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.main import create_app
from app.services.widget import WidgetService
from app.services.workspace import WorkspaceService


@pytest.fixture
async def app():
    app = create_app()
    yield app


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session():
    from app.core.database import async_session_maker
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def demo_workspace(db_session):
    """Create a demo workspace with user for testing."""
    service = WorkspaceService(db_session)
    workspace, user = await service.create_workspace_with_owner(
        email="submission_test@example.com",
        workspace_name="Submission Test Workspace",
        display_name="Submission Test User",
    )
    await db_session.commit()
    return workspace, user


@pytest.fixture
async def demo_user_token(demo_workspace):
    """Create a JWT token for the demo user."""
    workspace, user = demo_workspace
    token = create_access_token({"sub": str(user.id), "workspace_id": str(workspace.id)})
    return token, user, workspace


@pytest.fixture
async def demo_widget(db_session, demo_workspace):
    """Create a demo widget for testing."""
    workspace, user = demo_workspace
    service = WidgetService(db_session)
    widget = await service.create_widget(
        workspace_id=workspace.id,
        name="Submission Test Widget",
        configuration={
            "title": "Contact Us",
            "submit_label": "Send Message",
            "success_message": "Thanks!",
            "fields": [
                {"name": "name", "type": "text", "label": "Your Name", "required": True},
                {"name": "email", "type": "email", "label": "Email Address", "required": True},
                {"name": "message", "type": "textarea", "label": "Message", "required": False},
            ],
        },
    )
    await db_session.commit()
    return widget


class TestSubmissionHappyPath:
    """Test valid submission flow."""

    async def test_valid_submission_stored(self, client, demo_widget):
        """Test that a valid submission is stored and returns 201."""
        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "message": "Hello, world!",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Origin": "http://example.com"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "accepted"
        assert data["message"] == "Your submission has been received."
        assert "id" in data

    async def test_valid_submission_minimal_fields(self, client, demo_widget):
        """Test that a submission with only required fields is accepted."""
        payload = {
            "data": {
                "name": "Jane Doe",
                "email": "jane@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "accepted"


class TestSubmissionValidation:
    """Test validation of invalid submissions."""

    async def test_unknown_field_rejected(self, client, demo_widget):
        """Test that unknown fields are rejected."""
        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",  # Not in widget config
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422
        error = response.json()
        assert "detail" in error

    async def test_missing_required_field_rejected(self, client, demo_widget):
        """Test that missing required fields are rejected."""
        payload = {
            "data": {
                "email": "john@example.com",
                # Missing "name" which is required
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_empty_required_field_rejected(self, client, demo_widget):
        """Test that empty required fields are rejected."""
        payload = {
            "data": {
                "name": "",  # Empty required field
                "email": "john@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_field_too_long_rejected(self, client, demo_widget):
        """Test that fields exceeding max length are rejected."""
        payload = {
            "data": {
                "name": "A" * 2001,  # Exceeds 2000 char limit
                "email": "john@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_too_many_fields_rejected(self, client, demo_widget):
        """Test that exceeding max field count is rejected."""
        payload = {
            "data": {
                f"field_{i}": f"value_{i}" for i in range(21)  # Exceeds 20 field limit
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_oversized_payload_rejected(self, client, demo_widget):
        """Test that oversized request bodies are rejected (413)."""
        # Create a body > 1MB
        big_value = "x" * (1_000_000 + 1)
        payload = {
            "data": {
                "name": big_value,
                "email": "john@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Content-Length": str(len(json.dumps(payload)))},
        )
        assert response.status_code == 413


class TestSpamControl:
    """Test honeypot spam control."""

    async def test_honeypot_field_blocks_submission(self, client, demo_widget):
        """Test that filling the honeypot field rejects the submission."""
        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "website_url": "http://spam-bot.example.com",  # Honeypot filled
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 400
        error = response.json()
        assert "detail" in error

    async def test_honeypot_field_empty_allows_submission(self, client, demo_widget):
        """Test that empty honeypot field allows submission."""
        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "website_url": "",  # Empty honeypot - OK
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 201


class TestRateLimiting:
    """Test rate limiting on submission endpoint."""

    async def test_rate_limit_burst(self, client, demo_widget):
        """Test that a burst of requests triggers 429."""
        # Send 11 requests quickly (limit is 10/min per IP)
        responses = []
        for i in range(11):
            payload = {
                "data": {
                    "name": f"User {i}",
                    "email": f"user{i}@example.com",
                }
            }
            resp = await client.post(
                f"/public/v1/widgets/{demo_widget.public_id}/submissions",
                json=payload,
            )
            responses.append(resp.status_code)

        # First 10 should succeed (201), 11th should be 429
        assert responses[:10] == [201] * 10
        assert responses[10] == 429

    async def test_rate_limit_includes_retry_after(self, client, demo_widget):
        """Test that 429 responses include Retry-After header."""
        # Exhaust the rate limit
        for i in range(10):
            payload = {
                "data": {
                    "name": f"User {i}",
                    "email": f"user{i}@example.com",
                }
            }
            await client.post(
                f"/public/v1/widgets/{demo_widget.public_id}/submissions",
                json=payload,
            )

        # 11th request should be rate limited with Retry-After
        payload = {
            "data": {
                "name": "Blocked User",
                "email": "blocked@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 429
        assert "retry-after" in response.headers
        assert int(response.headers["retry-after"]) >= 1


class TestIdempotency:
    """Test idempotency key handling."""

    async def test_idempotency_replay_same_key_same_payload(self, client, demo_widget):
        """Test that retrying with same key and same payload returns replay."""
        idempotency_key = str(uuid.uuid4())
        payload = {
            "data": {
                "name": "Idempotent User",
                "email": "idempotent@example.com",
            }
        }

        # First submission
        response1 = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response1.status_code == 201
        id1 = response1.json()["id"]

        # Replay with same key and payload
        response2 = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response2.status_code == 201  # Replay returns success
        id2 = response2.json()["id"]
        assert id1 == id2  # Same submission, no duplicate

    async def test_idempotency_conflict_same_key_different_payload(self, client, demo_widget):
        """Test that same key with different payload returns 409."""
        idempotency_key = str(uuid.uuid4())
        payload1 = {
            "data": {
                "name": "User One",
                "email": "one@example.com",
            }
        }
        payload2 = {
            "data": {
                "name": "User Two",
                "email": "two@example.com",
            }
        }

        # First submission
        response1 = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload1,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response1.status_code == 201

        # Same key, different payload → conflict
        response2 = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload2,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response2.status_code == 409


class TestSubmissionFailureCases:
    """Test failure cases that should not lose submissions."""

    async def test_unknown_widget_rejected(self, client):
        """Test that unknown widget public ID returns 404."""
        import uuid
        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{uuid.uuid4()}/submissions",
            json=payload,
        )
        assert response.status_code == 404

    async def test_disabled_widget_rejected(self, client, db_session, demo_workspace):
        """Test that disabled widgets reject submissions."""
        from app.models import WidgetStatus
        workspace, user = demo_workspace
        service = WidgetService(db_session)
        widget = await service.create_widget(
            workspace_id=workspace.id,
            name="Disabled Widget",
            configuration={
                "title": "Disabled",
                "submit_label": "Submit",
                "success_message": "Thanks!",
                "fields": [{"name": "email", "type": "email", "label": "Email", "required": True}],
            },
        )
        await service.update_widget(
            widget_id=widget.id,
            workspace_id=workspace.id,
            status=WidgetStatus.DISABLED,
        )
        await db_session.commit()

        payload = {
            "data": {
                "email": "john@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 404


class TestSubmissionPersistence:
    """Test that submissions are durably stored."""

    async def test_submission_persisted_in_db(self, client, demo_widget, db_session):
        """Test that a successful submission is persisted in the database."""
        from sqlalchemy import select

        from app.models import Submission

        payload = {
            "data": {
                "name": "Persist Test",
                "email": "persist@example.com",
                "message": "Persistence check",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Verify in database
        result = await db_session.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        db_submission = result.scalar_one_or_none()
        assert db_submission is not None
        assert db_submission.data["name"] == "Persist Test"
        assert db_submission.data["email"] == "persist@example.com"
        assert db_submission.workspace_id == demo_widget.workspace_id
        assert db_submission.widget_id == demo_widget.id


class TestSubmissionHardeningRegressions:
    """Regression tests for issues found during Phase 5 validation."""

    async def test_wrong_field_type_rejected(self, client, demo_widget):
        """Non-string values for text/email fields are rejected (422)."""
        payload = {"data": {"name": "John", "email": 12345}}
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_wrong_field_type_object_rejected(self, client, demo_widget):
        payload = {"data": {"name": {"nested": "object"}, "email": "a@b.co"}}
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 422

    async def test_idempotency_key_too_long_rejected(self, client, demo_widget):
        """Oversized Idempotency-Key fails cleanly with 400, not a DB error."""
        payload = {"data": {"name": "John", "email": "john@example.com"}}
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Idempotency-Key": "k" * 256},
        )
        assert response.status_code == 400

    async def test_empty_honeypot_not_persisted(
        self, client, demo_widget, db_session
    ):
        """Empty honeypot is accepted and stripped from stored data."""
        from sqlalchemy import select

        from app.models import Submission

        payload = {
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "website_url": "",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]
        result = await db_session.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        submission = result.scalar_one()
        assert "website_url" not in submission.data

    async def test_idempotency_in_progress_returns_409(
        self, client, demo_widget, db_session
    ):
        """A claimed key with no linked submission must not create a duplicate."""
        import hashlib
        import json as jsonlib
        import uuid as uuidlib

        from app.models import IdempotencyRecord

        key = str(uuidlib.uuid4())
        data = {"name": "In Flight", "email": "inflight@example.com"}
        fingerprint = hashlib.sha256(
            jsonlib.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        db_session.add(
            IdempotencyRecord(
                workspace_id=demo_widget.workspace_id,
                widget_id=demo_widget.id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                submission_id=None,
            )
        )
        await db_session.commit()

        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json={"data": data},
            headers={"Idempotency-Key": key},
        )
        assert response.status_code == 409

    async def test_malformed_json_still_rate_limited(self, client, demo_widget):
        """Rate limiting runs before body parsing; malformed floods are capped."""
        statuses = []
        for _ in range(11):
            response = await client.post(
                f"/public/v1/widgets/{demo_widget.public_id}/submissions",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )
            statuses.append(response.status_code)
        assert statuses[:10] == [400] * 10
        assert statuses[10] == 429

    async def test_per_widget_rate_limit_enforced(
        self, client, demo_widget, monkeypatch
    ):
        """Widget-dimension limit triggers 429 independently of the IP limit."""
        from app.api.v1 import public as public_module

        monkeypatch.setattr(public_module.settings, "rate_limit_per_minute_ip", 100)
        monkeypatch.setattr(public_module.settings, "rate_limit_per_minute_widget", 3)

        statuses = []
        for i in range(5):
            response = await client.post(
                f"/public/v1/widgets/{demo_widget.public_id}/submissions",
                json={"data": {"name": f"U{i}", "email": f"u{i}@example.com"}},
            )
            statuses.append(response.status_code)
        assert statuses == [201, 201, 201, 429, 429]
        assert "retry-after" in response.headers
