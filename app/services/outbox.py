import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.repositories import OutboxRepository
from app.services.geo import GeoProvider, enrich_submission
from app.services.notifications import deliver_webhook, send_email_notification
from app.services.submission import SubmissionService

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(
        self,
        session: AsyncSession,
        provider_a: GeoProvider | None = None,
        provider_b: GeoProvider | None = None,
    ):
        self.outbox_repo = OutboxRepository(session)
        self.submission_service = SubmissionService(session)
        self.session = session
        self.provider_a = provider_a
        self.provider_b = provider_b

    async def process_job(self, job: OutboxEvent) -> bool:
        """Process a single outbox job. Returns True if succeeded, False if failed."""
        try:
            if job.event_type == "submission.geolocate":
                return await self._process_geolocate(job)
            elif job.event_type == "submission.send_notification":
                return await self._process_notification(job)
            elif job.event_type == "submission.deliver_webhook":
                return await self._process_webhook(job)
            else:
                logger.warning(
                    "Unknown job type", extra={"job_id": str(job.id), "event_type": job.event_type}
                )
                return False
        except Exception as e:
            logger.exception(
                "Job processing failed",
                extra={"job_id": str(job.id), "event_type": job.event_type, "error": str(e)},
            )
            return False

    async def _process_geolocate(self, job: OutboxEvent) -> bool:
        submission_id = UUID(job.payload["submission_id"])
        workspace_id = job.workspace_id
        if workspace_id is None:
            logger.warning(
                "Job missing workspace_id", extra={"job_id": str(job.id)}
            )
            return False
        submission = await self.submission_service.get_submission(
            submission_id, workspace_id
        )
        if not submission:
            logger.warning(
                "Submission not found for geolocation",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
            return False

        # Use the client IP captured at submission time for geolocation.
        client_ip = submission.client_ip or ""
        result = await enrich_submission(
            client_ip,
            provider_a=self.provider_a,
            provider_b=self.provider_b,
        )

        if result:
            await self.submission_service.submission_repo.update_enrichment(
                submission_id=submission_id,
                country_code=result.country_code,
                country_name=result.country_name,
                region=result.region,
                city=result.city,
                latitude=result.latitude,
                longitude=result.longitude,
                enrichment_status="completed",
            )
            logger.info(
                "Geolocation enrichment completed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
        else:
            await self.submission_service.submission_repo.update_enrichment(
                submission_id=submission_id, enrichment_status="failed"
            )
            logger.warning(
                "Geolocation enrichment failed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )

        return True

    async def _process_notification(self, job: OutboxEvent) -> bool:
        """Send email notification for a new submission."""
        submission_id = UUID(job.payload["submission_id"])
        workspace_id = job.workspace_id
        if workspace_id is None:
            logger.warning(
                "Job missing workspace_id", extra={"job_id": str(job.id)}
            )
            return False
        submission = await self.submission_service.get_submission(
            submission_id, workspace_id
        )
        if not submission:
            logger.warning(
                "Submission not found for notification",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
            return False

        # Stub implementation — logs only. In production, this would call
        # an SMTP provider. The function is injected via unittest.mock.patch
        # in tests to simulate delivery failures deterministically.
        success = await send_email_notification(
            submission_id=submission_id,
            workspace_id=workspace_id,
            to_email="owner@example.com",  # Would come from workspace config
            subject="New lead submission",
            body=f"A new lead was submitted via widget {submission.widget_id}.",
        )
        if success:
            await self.submission_service.submission_repo.update_enrichment(
                submission_id=submission_id,
                notification_status="sent",
            )
            logger.info(
                "Notification job processed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
        else:
            logger.warning(
                "Notification job failed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
        return success

    async def _process_webhook(self, job: OutboxEvent) -> bool:
        """Deliver webhook for a new submission."""
        submission_id = UUID(job.payload["submission_id"])
        workspace_id = job.workspace_id
        if workspace_id is None:
            logger.warning(
                "Job missing workspace_id", extra={"job_id": str(job.id)}
            )
            return False
        submission = await self.submission_service.get_submission(
            submission_id, workspace_id
        )
        if not submission:
            logger.warning(
                "Submission not found for webhook",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
            return False

        # Stub implementation — logs only. In production, this would POST
        # to the configured webhook URL with HMAC signature. Injected via
        # unittest.mock.patch in tests to simulate delivery failures.
        success = await deliver_webhook(
            submission_id=submission_id,
            workspace_id=workspace_id,
            url="https://example.com/webhook",  # Would come from workspace config
            payload={"submission_id": str(submission_id)},
        )
        if success:
            logger.info(
                "Webhook job processed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
        else:
            logger.warning(
                "Webhook job failed",
                extra={"job_id": str(job.id), "submission_id": str(submission_id)},
            )
        return success
