"""Phase 6 worker/outbox integration tests.

Covers client_ip persistence, atomic outbox creation, claim/complete,
retry scheduling, backoff, dead-lettering, stale-lock recovery, provider
injection through the real geolocate path, and worker batch processing.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_maker
from app.main import create_app
from app.models import JobStatus, OutboxEvent, Submission
from app.repositories import OutboxRepository
from app.services.geo import GeoProvider, GeoResult
from app.services.outbox import OutboxProcessor
from app.services.widget import WidgetService
from app.services.workspace import WorkspaceService


@pytest.fixture
async def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def demo_workspace(db_session):
    service = WorkspaceService(db_session)
    workspace, user = await service.create_workspace_with_owner(
        email="worker_test@example.com",
        workspace_name="Worker Test Workspace",
        display_name="Worker Test User",
    )
    await db_session.commit()
    return workspace, user


@pytest.fixture
async def demo_widget(db_session, demo_workspace):
    workspace, user = demo_workspace
    service = WidgetService(db_session)
    widget = await service.create_widget(
        workspace_id=workspace.id,
        name="Worker Test Widget",
        configuration={
            "title": "Worker Test",
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


async def _submit(client, widget):
    response = await client.post(
        f"/public/v1/widgets/{widget.public_id}/submissions",
        json={"data": {"name": "Worker", "email": "worker@example.com"}},
    )
    assert response.status_code == 201
    return response.json()["id"]


class FakeProvider(GeoProvider):
    def __init__(self, result: GeoResult | None):
        self.result = result
        self.calls: list[str] = []

    async def lookup(self, ip: str) -> GeoResult | None:
        self.calls.append(ip)
        return self.result


class TestSubmissionSideEffects:
    async def test_client_ip_persisted_with_submission(self, client, demo_widget):
        submission_id = await _submit(client, demo_widget)
        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            assert stored.client_ip is not None
            # httpx ASGITransport reports the peer as 127.0.0.1
            assert stored.client_ip == "127.0.0.1"

    async def test_outbox_events_created_with_submission(
        self, client, demo_widget, db_session
    ):
        """Geolocate + notification jobs are committed with the submission."""
        submission_id = await _submit(client, demo_widget)
        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.submission_id == submission_id)
        )
        events = result.scalars().all()
        types = sorted(e.event_type for e in events)
        assert types == ["submission.geolocate", "submission.send_notification"]
        for event in events:
            assert event.status == JobStatus.PENDING
            assert event.workspace_id == demo_widget.workspace_id
            assert event.payload == {"submission_id": str(submission_id)}


class TestClaimCompleteCycle:
    async def test_claim_marks_running_and_complete_persists(
        self, db_session, demo_widget
    ):
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.geolocate",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )
        await db_session.commit()

        claimed = await repo.claim_jobs("worker-1", limit=10)
        assert [j.id for j in claimed] == [event.id]
        assert event.status == JobStatus.RUNNING
        assert event.attempt_count == 1
        assert event.locked_by == "worker-1"

        await repo.complete_job(event)
        await db_session.commit()
        assert event.status == JobStatus.SUCCEEDED

    async def test_completed_job_is_not_claimed_again(
        self, db_session, demo_widget
    ):
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.geolocate",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )
        await repo.claim_jobs("worker-1")
        await repo.complete_job(event)
        await db_session.commit()

        again = await repo.claim_jobs("worker-2")
        assert again == []

    async def test_retrying_job_with_elapsed_backoff_is_claimable(
        self, db_session, demo_widget
    ):
        """Regression: claim_jobs used to select only PENDING jobs, so
        RETRYING jobs (every retry) were never picked up again."""
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.send_notification",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )
        await repo.claim_jobs("worker-1")
        await repo.fail_job(event, "NOTIFICATION_FAILED")
        assert event.status == JobStatus.RETRYING
        await db_session.commit()

        # Backoff not yet elapsed → not claimable
        assert await repo.claim_jobs("worker-1") == []

        # Simulate elapsed backoff
        event.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()

        claimed = await repo.claim_jobs("worker-1")
        assert [j.id for j in claimed] == [event.id]
        assert event.attempt_count == 2


class TestBackoffAndDeadLetter:
    async def test_backoff_schedule_is_exponential(self, db_session, demo_widget):
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.send_notification",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )

        # Failures 1-4 retry with 5s, 15s, 45s, 120s; failure 5 dead-letters
        expected_delays = [5, 15, 45, 120]
        for expected in expected_delays:
            await repo.claim_jobs("worker-1")
            before = datetime.now(UTC)
            await repo.fail_job(event, "FAILED")
            delay = (event.available_at - before).total_seconds()
            assert expected - 1 <= delay <= expected + 2, (
                f"expected ~{expected}s, got {delay}s"
            )
            assert event.status == JobStatus.RETRYING
            # make due for the next claim
            event.available_at = datetime.now(UTC) - timedelta(seconds=1)
            await db_session.flush()

        # Sixth failure at max attempts → dead letter
        await repo.claim_jobs("worker-1")
        await repo.fail_job(event, "FAILED")
        assert event.status == JobStatus.DEAD_LETTER
        assert await repo.claim_jobs("worker-1") == []
        assert await repo.get_dead_letter_count() == 1
        await db_session.commit()


class TestStaleLockRecovery:
    async def test_stale_running_job_is_released_and_reclaimable(
        self, db_session, demo_widget
    ):
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.geolocate",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )
        await repo.claim_jobs("crashed-worker")
        # Simulate a lock older than the 300s stale threshold
        event.locked_at = datetime.now(UTC) - timedelta(seconds=400)
        await db_session.commit()

        released = await repo.release_stale_locks()
        assert released == 1
        # release_stale_locks issues a core UPDATE; refresh the ORM instance
        await db_session.refresh(event)
        assert event.status == JobStatus.PENDING
        assert event.locked_by is None
        await db_session.commit()

        claimed = await repo.claim_jobs("fresh-worker")
        assert [j.id for j in claimed] == [event.id]
        assert event.locked_by == "fresh-worker"

    async def test_fresh_lock_is_not_released(self, db_session, demo_widget):
        repo = OutboxRepository(db_session)
        event = await repo.create(
            event_type="submission.geolocate",
            payload={"submission_id": str(uuid4())},
            workspace_id=demo_widget.workspace_id,
        )
        await repo.claim_jobs("busy-worker")
        await db_session.commit()

        released = await repo.release_stale_locks()
        assert released == 0
        assert event.status == JobStatus.RUNNING
        await db_session.rollback()


class TestInjectedProvidersThroughProcessor:
    async def test_geolocate_uses_injected_providers_and_client_ip(
        self, client, db_session, demo_widget
    ):
        submission_id = await _submit(client, demo_widget)
        # Overwrite the captured IP to a known value
        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            stored.client_ip = "203.0.113.9"
            workspace_id = stored.workspace_id
            await session.commit()

        provider_a = FakeProvider(None)  # fails
        provider_b = FakeProvider(
            GeoResult(country_code="US", country_name="United States")
        )

        async with async_session_maker() as session:
            processor = OutboxProcessor(
                session, provider_a=provider_a, provider_b=provider_b
            )
            job = OutboxEvent(
                workspace_id=workspace_id,
                submission_id=submission_id,
                event_type="submission.geolocate",
                payload={"submission_id": str(submission_id)},
            )
            success = await processor.process_job(job)
            await session.commit()
            assert success is True

        # Real code path: providers injected, captured IP forwarded, B used
        assert provider_a.calls == ["203.0.113.9"]
        assert provider_b.calls == ["203.0.113.9"]

        async with async_session_maker() as session:
            enriched = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            assert enriched.country_code == "US"
            assert enriched.enrichment_status == "completed"

    async def test_notification_success_sets_notification_status(
        self, client, db_session, demo_widget
    ):
        submission_id = await _submit(client, demo_widget)
        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            workspace_id = stored.workspace_id

        with patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=True),
        ):
            async with async_session_maker() as session:
                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.send_notification",
                    payload={"submission_id": str(submission_id)},
                )
                success = await processor.process_job(job)
                await session.commit()
                assert success is True

        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            assert stored.notification_status == "sent"

    async def test_webhook_success_completes_job(
        self, client, db_session, demo_widget
    ):
        submission_id = await _submit(client, demo_widget)
        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            workspace_id = stored.workspace_id

        with patch(
            "app.services.outbox.deliver_webhook",
            new=AsyncMock(return_value=True),
        ) as mock_webhook:
            async with async_session_maker() as session:
                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.deliver_webhook",
                    payload={"submission_id": str(submission_id)},
                )
                success = await processor.process_job(job)
                await session.commit()
                assert success is True
                mock_webhook.assert_called_once()

    async def test_failed_email_leaves_notification_status_unset(
        self, client, db_session, demo_widget
    ):
        submission_id = await _submit(client, demo_widget)
        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            workspace_id = stored.workspace_id

        with patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=False),
        ):
            async with async_session_maker() as session:
                processor = OutboxProcessor(session)
                job = OutboxEvent(
                    workspace_id=workspace_id,
                    submission_id=submission_id,
                    event_type="submission.send_notification",
                    payload={"submission_id": str(submission_id)},
                )
                success = await processor.process_job(job)
                await session.commit()
                assert success is False

        async with async_session_maker() as session:
            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            assert stored.notification_status is None


class TestWorkerBatch:
    async def test_process_batch_completes_all_due_jobs(
        self, client, db_session, demo_widget
    ):
        """End-to-end: Worker._process_batch claims, processes, and commits."""
        from scripts.worker import Worker

        submission_id = await _submit(client, demo_widget)

        geo_result = GeoResult(country_code="US", country_name="United States")
        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=geo_result),
        ), patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=True),
        ), patch(
            "app.services.outbox.deliver_webhook",
            new=AsyncMock(return_value=True),
        ):
            worker = Worker()
            await worker._process_batch()

        async with async_session_maker() as session:
            events = (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.submission_id == submission_id
                    )
                )
            ).scalars().all()
            assert len(events) == 2
            assert all(e.status == JobStatus.SUCCEEDED for e in events)

            stored = (
                await session.execute(
                    select(Submission).where(Submission.id == submission_id)
                )
            ).scalar_one()
            assert stored.enrichment_status == "completed"
            assert stored.country_code == "US"
            assert stored.notification_status == "sent"

    async def test_process_batch_is_idempotent_on_rerun(
        self, client, db_session, demo_widget
    ):
        """Running the batch again after completion must not reprocess."""
        from scripts.worker import Worker

        submission_id = await _submit(client, demo_widget)

        with patch(
            "app.services.outbox.enrich_submission",
            new=AsyncMock(return_value=GeoResult(country_code="US")),
        ), patch(
            "app.services.outbox.send_email_notification",
            new=AsyncMock(return_value=True),
        ):
            worker = Worker()
            await worker._process_batch()
            # Second run: nothing due → no state changes, no errors
            await worker._process_batch()

        async with async_session_maker() as session:
            events = (
                await session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.submission_id == submission_id
                    )
                )
            ).scalars().all()
            assert all(e.status == JobStatus.SUCCEEDED for e in events)
            assert all(e.attempt_count == 1 for e in events)
