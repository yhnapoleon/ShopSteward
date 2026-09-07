from typing import Annotated

from asyncpg import PostgresError
from fastapi import Path, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import Admin, User
from app.api.routing import B0Router, errors
from app.api.schemas import Health, JobRun, MonitoringStatus
from app.core.errors import AppError

router = B0Router()


@router.get("/health/live", response_model=Health, operation_id="health_live", tags=["Health"])
async def live():
    return Health(status="ok", component="backend")


@router.get(
    "/health/ready",
    response_model=Health,
    operation_id="health_ready",
    tags=["Health"],
    responses={503: {"model": Health}},
)
async def ready(request: Request, response: Response):
    try:
        available = await request.app.state.db.ready()
    except (AppError, SQLAlchemyError, PostgresError, OSError, TimeoutError):
        available = False
    response.status_code = 200 if available else 503
    return Health(status="ok" if available else "unavailable", component="backend")


@router.get(
    "/api/v1/monitoring/status",
    response_model=MonitoringStatus,
    operation_id="get_monitoring_status",
    tags=["Monitoring"],
    responses=errors,
)
async def monitoring(request: Request, principal: Admin):
    from app.scheduling.repository import monitoring_status

    async with request.app.state.db.session() as session:
        return await monitoring_status(
            session,
            request.app.state.settings.job_lease_seconds,
            request.app.state.settings.source_stale_seconds,
        )


@router.get(
    "/api/v1/job-runs/{job_run_id}",
    response_model=JobRun,
    response_model_exclude_unset=True,
    operation_id="get_job_run",
    tags=["Scheduling"],
    responses=errors,
)
async def get_job(
    request: Request,
    principal: User,
    job_run_id: Annotated[str, Path(min_length=1, max_length=128)],
):
    from app.scheduling.models import Job

    async with request.app.state.db.session() as session:
        job = await session.get(Job, job_run_id)
        if job is None:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Job is not visible or does not exist")
        if "admin" not in principal.roles and (
            not principal.roles or job.store_id is None or job.store_id not in principal.store_ids
        ):
            raise AppError(404, "RESOURCE_NOT_FOUND", "Job is not visible or does not exist")
        return JobRun.model_validate(job)
