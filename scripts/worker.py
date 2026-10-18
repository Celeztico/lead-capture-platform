import asyncio
import logging
import signal
import uuid

from app.core.database import async_session_maker
from app.repositories import OutboxRepository
from app.services.outbox import OutboxProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("worker")


class Worker:
    def __init__(self):
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.running = False
        self.poll_interval = 5  # seconds
        self.batch_size = 10

    async def run(self):
        self.running = True
        logger.info(f"Worker started: {self.worker_id}")

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        while self.running:
            try:
                await self._process_batch()
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")

            await asyncio.sleep(self.poll_interval)

        logger.info(f"Worker stopped: {self.worker_id}")

    def _shutdown(self):
        logger.info("Shutdown signal received")
        self.running = False

    async def _process_batch(self):
        async with async_session_maker() as session:
            outbox_repo = OutboxRepository(session)
            processor = OutboxProcessor(session)

            # Release stale locks first
            released = await outbox_repo.release_stale_locks()
            if released:
                logger.info(f"Released {released} stale job locks")

            # Claim jobs
            jobs = await outbox_repo.claim_jobs(self.worker_id, self.batch_size)

            for job in jobs:
                try:
                    success = await processor.process_job(job)
                    if success:
                        await outbox_repo.complete_job(job)
                        logger.info(
                            "Job completed",
                            extra={
                                "job_id": str(job.id),
                                "event_type": job.event_type,
                                "attempt": job.attempt_count,
                            },
                        )
                    else:
                        await outbox_repo.fail_job(job, "PROCESSING_FAILED")
                        logger.warning(
                            "Job failed",
                            extra={
                                "job_id": str(job.id),
                                "event_type": job.event_type,
                                "attempt": job.attempt_count,
                            },
                        )
                except Exception as e:
                    logger.exception(f"Error processing job {job.id}: {e}")
                    await outbox_repo.fail_job(job, "EXCEPTION")

            await session.commit()


async def main():
    worker = Worker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
