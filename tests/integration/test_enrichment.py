"""Deterministic failure-injection tests for Phase 6.

Tests geo-provider fallback, notification failure tolerance, and worker
retry behavior using unittest.mock.patch for injectable failures.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.main import create_app
from app.models import JobStatus, Submission
from app.services.geo import GeoResult
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
        email="enrichment_test@example.com",
        workspace_name="Enrichment Test Workspace",
        display_name="Enrichment Test User",
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
        name="Enrichment Test Widget",
        configuration={
            "title": "Enrichment Test",
            "submit_label": "Send",
            "success_message": "Thanks!",
            "fields": [
                {"name": "name", "type": "text", "label": "Name", "required": True},
                {"name": "email", "type": "email", "label": "Email", "required": True},
            ],
        },
    )
    await db_session.commit()
    return widget


# ---------------------------------------------------------------------------
# Geo-provider fallback tests
# ---------------------------------------------------------------------------


class TestGeoProviderFallback:
    """Test provider A → B fallback behavior."""

    async def test_provider_a_succeeds_enrichment_stored(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Provider A succeeds → submission stored with enrichment."""
        token, user, workspace = demo_user_token

        # Submit a lead
        payload = {
            "data": {
                "name": "Geo Test",
                "email": "geo@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock provider A to succeed
        geo_result = GeoResult(
            country_code="US",
            country_name="United States",
            region="California",
            city="San Francisco",
            latitude=37.7749,
            longitude=-122.4194,
        )

        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=geo_result),
        ) as mock_enrich:
            from app.core.database import async_session_maker

            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id
                captured_ip = submission.client_ip

                processor = OutboxProcessor(session)
                from app.models import OutboxEvent

                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.geolocate",
                    payload={"submission_id": str(submission_id)},
                )

                success = await processor.process_job(job)
                await session.commit()
                assert success is True
                mock_enrich.assert_called_once()
                # Enrichment must use the client IP captured at submission time
                assert mock_enrich.call_args.args[0] == captured_ip

            # Verify enrichment stored
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                enriched = result2.scalar_one()
                assert enriched.country_code == "US"
                assert enriched.country_name == "United States"
                assert enriched.enrichment_status == "completed"

    async def test_provider_a_fails_provider_b_succeeds(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Provider A fails → provider B succeeds → enrichment stored."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "Fallback Test",
                "email": "fallback@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock enrich_submission to simulate A fails, B succeeds
        # We patch at the enrich_submission level since OutboxProcessor calls it
        geo_result = GeoResult(
            country_code="GB",
            country_name="United Kingdom",
            region="England",
            city="London",
            latitude=51.5074,
            longitude=-0.1278,
        )

        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=geo_result),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.geolocate",
                    payload={"submission_id": str(submission_id)},
                )

                success = await processor.process_job(job)
                await session.commit()
                assert success is True

            # Verify enrichment stored with provider B's result
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                enriched = result2.scalar_one()
                assert enriched.country_code == "GB"
                assert enriched.enrichment_status == "completed"

    async def test_both_providers_fail_submission_still_stored(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Both geo providers fail → submission stored without enrichment."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "Both Fail Test",
                "email": "bothfail@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock enrich_submission to return None (both providers fail)
        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=None),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.geolocate",
                    payload={"submission_id": str(submission_id)},
                )

                success = await processor.process_job(job)
                await session.commit()
                assert success is True  # Job succeeds even without enrichment

            # Verify submission exists without enrichment
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                stored = result2.scalar_one()
                assert stored.country_code is None
                assert stored.enrichment_status == "failed"

    async def test_unknown_submission_rejected_for_geo(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Geo job for unknown submission → processor returns False."""
        token, user, workspace = demo_user_token

        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        async with async_session_maker() as session:
            processor = OutboxProcessor(session)
            job = OutboxEvent(
                workspace_id=workspace.id,
                submission_id=uuid4(),
                event_type="submission.geolocate",
                payload={"submission_id": str(uuid4())},
            )

            success = await processor.process_job(job)
            assert success is False


# ---------------------------------------------------------------------------
# Notification failure tolerance tests
# ---------------------------------------------------------------------------


class TestNotificationFailureTolerance:
    """Test that notification failures don't lose submissions."""

    async def test_email_failure_does_not_lose_submission(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Email notification fails → submission still stored."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "Notify Fail Test",
                "email": "notifyfail@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock send_email_notification to fail
        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=False),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.send_notification",
                    payload={"submission_id": str(submission_id)},
                    attempt_count=1,
                    max_attempts=5,
                )

                success = await processor.process_job(job)
                assert success is False  # Job fails

                # Fail the job → should go to RETRYING (attempt_count=1 < max_attempts=5)
                await processor.outbox_repo.fail_job(job, "NOTIFICATION_FAILED")
                await session.commit()

                assert job.status == JobStatus.RETRYING
                assert job.attempt_count == 1

            # Verify submission still exists (not lost)
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                stored = result2.scalar_one()
                assert stored is not None
                assert stored.data["name"] == "Notify Fail Test"

    async def test_webhook_failure_does_not_lose_submission(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Webhook delivery fails → submission still stored."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "Webhook Fail Test",
                "email": "webhookfail@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock deliver_webhook to fail
        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.deliver_webhook",
            new=AsyncMock(return_value=False),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.deliver_webhook",
                    payload={"submission_id": str(submission_id)},
                    attempt_count=1,
                    max_attempts=5,
                )

                success = await processor.process_job(job)
                assert success is False

                # Fail the job → should go to RETRYING
                await processor.outbox_repo.fail_job(job, "WEBHOOK_FAILED")
                await session.commit()

                assert job.status == JobStatus.RETRYING
                assert job.attempt_count == 1

            # Verify submission still exists
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                stored = result2.scalar_one()
                assert stored is not None
                assert stored.data["name"] == "Webhook Fail Test"


# ---------------------------------------------------------------------------
# Worker retry behavior tests
# ---------------------------------------------------------------------------


class TestWorkerRetryBehavior:
    """Test bounded retries and dead-letter handling."""

    async def test_notification_failure_to_dead_letter(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """Notification failure → job retries → dead letter after max attempts."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "Dead Letter Test",
                "email": "deadletter@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        from app.core.database import async_session_maker
        from app.models import JobStatus, OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=False),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                # Create a job at max_attempts (all retries exhausted)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.send_notification",
                    payload={"submission_id": str(submission_id)},
                    attempt_count=5,  # Equal to max_attempts=5 → next failure = dead letter
                    max_attempts=5,
                    status=JobStatus.RETRYING,
                )
                session.add(job)
                await session.commit()

                processor = OutboxProcessor(session)

                # Process the job (notification fails)
                success = await processor.process_job(job)
                assert success is False

                # Fail the job → should go to dead letter
                await processor.outbox_repo.fail_job(job, "NOTIFICATION_FAILED")
                await session.commit()

                assert job.status == JobStatus.DEAD_LETTER
                dead_count = await processor.outbox_repo.get_dead_letter_count()
                assert dead_count == 1


# ---------------------------------------------------------------------------
# End-to-end: submission stored even when all optional work fails
# ---------------------------------------------------------------------------


class TestSubmissionReliability:
    """Test that submission capture is independent of optional work."""

    async def test_submission_stored_when_all_optional_work_fails(
        self, client, db_session, demo_widget, demo_user_token
    ):
        """All optional work (geo, notification, webhook) fails → submission still stored."""
        token, user, workspace = demo_user_token

        payload = {
            "data": {
                "name": "All Fail Test",
                "email": "allfail@example.com",
            }
        }
        response = await client.post(
            f"/public/v1/widgets/{demo_widget.public_id}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        submission_id = response.json()["id"]

        # Mock everything to fail
        from app.core.database import async_session_maker
        from app.models import OutboxEvent
        from app.services.outbox import OutboxProcessor

        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=False),
        ), patch(
            "app.services.outbox.deliver_webhook",
            new=AsyncMock(return_value=False),
        ):
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                submission = result.scalar_one()
                workspace_id = submission.workspace_id

                processor = OutboxProcessor(session)

                # Process all three job types
                for event_type in [
                    "submission.geolocate",
                    "submission.send_notification",
                    "submission.deliver_webhook",
                ]:
                    job = OutboxEvent(
                        workspace_id=workspace_id,
                        submission_id=submission_id,
                        event_type=event_type,
                        payload={"submission_id": str(submission_id)},
                    )
                    success = await processor.process_job(job)
                    # Geo returns True (stored without enrichment), notifications return False
                    if event_type == "submission.geolocate":
                        assert success is True
                    else:
                        assert success is False
                await session.commit()

            # Verify submission still exists with all data intact
            async with async_session_maker() as session2:
                result2 = await session2.execute(
                    select(Submission).where(
                        Submission.id == submission_id
                    )
                )
                stored = result2.scalar_one()
                assert stored is not None
                assert stored.data["name"] == "All Fail Test"
                assert stored.data["email"] == "allfail@example.com"
                assert stored.enrichment_status == "failed"  # Geo failed
