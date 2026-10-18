import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent
from app.repositories import OutboxRepository
from app.services.geo import enrich_submission
from app.services.submission import SubmissionService

logger = logging.getLogger(__name__)


class OutboxProcessor:
    def __init__(self, session: AsyncSession):
        self.outbox_repo = OutboxRepository(session)
        self.submission_service = SubmissionService(session)
        self.session = session

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

        # For demo, use a test IP. In production, extract from submission.source_origin
        # or store IP separately. Using a known test IP.
        test_ip = "8.8.8.8"  # Google DNS - test IP
        result = await enrich_submission(test_ip)

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
        # Stub - would send email to workspace owner
        logger.info(
            "Notification job processed (stub)",
            extra={"job_id": str(job.id)},
        )
        return True

    async def _process_webhook(self, job: OutboxEvent) -> bool:
        # Stub - would deliver webhook
        logger.info(
            "Webhook job processed (stub)",
            extra={"job_id": str(job.id)},
        )
        return True
