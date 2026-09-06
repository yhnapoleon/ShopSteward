import asyncio
import logging
from uuid import uuid4

from app.core.errors import AppError
from app.scheduling import repository as repo
from app.scheduling.handlers import HANDLERS

logger = logging.getLogger("shopsteward")


async def wait_or_stop(event: asyncio.Event, seconds: float):
    try:
        await asyncio.wait_for(event.wait(), timeout=seconds)
    except TimeoutError:
        pass


class Runner:
    def __init__(self, db, settings, *, worker_id=None, handlers=None):
        self.db = db
        self.settings = settings
        self.worker_id = worker_id or str(uuid4())
        if handlers is None:
            from app.operations.jobs import make_handlers
            from app.planning.jobs import make_handler

            self.handlers = dict(HANDLERS) | make_handlers(settings)
            self.handlers["check_mission"] = make_handler(settings)
            from app.execution.jobs import make_handlers as execution_handlers

            self.handlers.update(execution_handlers(settings))
        else:
            self.handlers = dict(handlers)

    async def run_once(self, stop: asyncio.Event | None = None) -> bool:
        if stop is not None and stop.is_set():
            return False
        if "reconcile_action" in self.handlers:
            from app.execution.jobs import recover_actions

            await recover_actions(self.db)
        async with self.db.session() as session, session.begin():
            await repo.heartbeat(session, self.worker_id)
            await repo.recover_expired(
                session,
                retry_safe_types=[
                    name for name, handler in self.handlers.items() if handler.retry_safe
                ],
            )
            if stop is not None and stop.is_set():
                return False
            job = await repo.claim(
                session,
                lease_seconds=self.settings.job_lease_seconds,
                job_types=list(self.handlers),
            )
            if stop is not None and stop.is_set():
                await session.rollback()
                return False
        if job is None:
            return False
        done, lost = asyncio.Event(), asyncio.Event()
        renewal = asyncio.create_task(self._renew(job, done, lost))
        try:
            async with asyncio.timeout(self.settings.job_timeout_seconds):
                result = await self.handlers[job.job_type].run(self.db, job)
                if not lost.is_set():
                    async with self.db.session() as session, session.begin():
                        apply = self.handlers[job.job_type].apply
                        if apply is not None:
                            result = await apply(session, job, result)
                        accepted = await repo.complete(session, job.id, job.lease_token, result)
                        if not accepted:
                            # The lease fence covers all derived writes, not only job status.
                            await session.rollback()
                        elif self.handlers[job.job_type].after_complete is not None:
                            await self.handlers[job.job_type].after_complete(session, job, result)
                    logger.info(
                        "job_succeeded" if accepted else "job_lease_lost",
                        extra={"job_run_id": job.id, "worker_id": self.worker_id},
                    )
        except asyncio.CancelledError:
            # Cancellation leaves RUNNING for lease recovery, never a fabricated failure.
            raise
        except Exception as exc:
            logger.error(
                "job_failed", extra={"job_run_id": job.id, "error_type": type(exc).__name__}
            )
            if self.handlers[job.job_type].retry_safe and not lost.is_set():
                async with self.db.session() as session, session.begin():
                    from app.execution.events import EventActionConflict, persist_conflict

                    if isinstance(exc, EventActionConflict):
                        await persist_conflict(session, exc)
                        if not await repo.renew(
                            session, job.id, job.lease_token, self.settings.job_lease_seconds
                        ):
                            await session.rollback()
                            return True
                    await repo.fail(
                        session,
                        job.id,
                        job.lease_token,
                        exc.code if isinstance(exc, AppError) else "HANDLER_FAILED",
                        retryable=isinstance(exc, AppError) and exc.retryable,
                    )
            # Action recovery handles uncertain external writes independently of JobRun failure.
        finally:
            done.set()
            await renewal
        return True

    async def _renew(self, job, done, lost):
        while not done.is_set():
            await wait_or_stop(done, self.settings.job_heartbeat_seconds)
            if done.is_set():
                return
            try:
                async with self.db.session() as session, session.begin():
                    valid = await repo.renew(
                        session, job.id, job.lease_token, self.settings.job_lease_seconds
                    )
                if not valid:
                    lost.set()
                    return
            except Exception as exc:
                lost.set()
                logger.warning(
                    "lease_renewal_failed",
                    extra={"job_run_id": job.id, "error_type": type(exc).__name__},
                )
                return

    async def _pulse(self, stop):
        while not stop.is_set():
            try:
                async with self.db.session() as session, session.begin():
                    await repo.heartbeat(session, self.worker_id)
            except Exception as exc:
                logger.warning(
                    "worker_heartbeat_failed",
                    extra={"worker_id": self.worker_id, "error_type": type(exc).__name__},
                )
            await wait_or_stop(stop, self.settings.job_heartbeat_seconds)

    async def serve(self, stop: asyncio.Event):
        pulse_stop = asyncio.Event()
        pulse = asyncio.create_task(self._pulse(pulse_stop))
        active = set()
        try:
            while not stop.is_set():
                finished = {task for task in active if task.done()}
                for task in finished:
                    try:
                        task.result()
                    except Exception as exc:
                        logger.error(
                            "worker_iteration_failed",
                            extra={
                                "worker_id": self.worker_id,
                                "error_type": type(exc).__name__,
                            },
                        )
                active -= finished
                for _ in range(self.settings.worker_concurrency - len(active)):
                    active.add(asyncio.create_task(self.run_once(stop)))
                await wait_or_stop(stop, self.settings.worker_poll_seconds)
        finally:
            if active:
                _, pending = await asyncio.wait(
                    active, timeout=self.settings.worker_shutdown_seconds
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*active, return_exceptions=True)
            pulse_stop.set()
            await pulse
            async with self.db.session() as session, session.begin():
                await repo.heartbeat(session, self.worker_id, "STOPPED")
