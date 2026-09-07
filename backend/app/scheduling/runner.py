import asyncio
import logging
from uuid import uuid4

from app.core.errors import AppError
from app.scheduling import repository as repo

logger = logging.getLogger("shopsteward")


async def wait_or_stop(event: asyncio.Event, seconds: float):
    try:
        await asyncio.wait_for(event.wait(), timeout=seconds)
    except TimeoutError:
        pass


class Runner:
    def __init__(self, db, settings, *, worker_id=None, handlers=None, dispatcher=None):
        self.db = db
        self.settings = settings
        self.worker_id = worker_id or str(uuid4())
        if handlers is None:
            from app.bootstrap import make_handlers
            from app.scheduling.dispatcher import dispatch_due

            handlers = make_handlers(settings)
            dispatcher = dispatcher or dispatch_due
        self.dispatcher = dispatcher
        self.handlers = dict(handlers)
        self.before_claim = tuple(
            dict.fromkeys(
                handler.before_claim for handler in self.handlers.values() if handler.before_claim
            )
        )

    async def run_once(self, stop: asyncio.Event | None = None) -> bool:
        if stop is not None and stop.is_set():
            return False
        for hook in self.before_claim:
            await hook(self.db)
            if stop is not None and stop.is_set():
                return False
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
                    on_error = self.handlers[job.job_type].on_error
                    if on_error is not None:
                        await on_error(session, job, exc)
                    # Business locks precede the job lock, as in successful publication.
                    accepted = await repo.fail(
                        session,
                        job.id,
                        job.lease_token,
                        exc.code if isinstance(exc, AppError) else "HANDLER_FAILED",
                        retryable=isinstance(exc, AppError) and exc.retryable,
                    )
                    if not accepted:
                        await session.rollback()
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

    async def _dispatch(self, stop):
        while not stop.is_set():
            try:
                await self.dispatcher(self.db)
            except Exception as exc:
                logger.error("schedule_dispatch_failed", extra={"error_type": type(exc).__name__})
            await wait_or_stop(stop, self.settings.worker_poll_seconds)

    async def serve(self, stop: asyncio.Event):
        pulse_stop = asyncio.Event()
        pulse = asyncio.create_task(self._pulse(pulse_stop))
        dispatch = asyncio.create_task(self._dispatch(stop)) if self.dispatcher else None
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
            if dispatch is not None:
                dispatch.cancel()
                await asyncio.gather(dispatch, return_exceptions=True)
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
