import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from test_missions import environment, fresh_seed, headers, settings
from test_operations import initialize, state

pytestmark = pytest.mark.integration


async def test_advance_requires_admin_and_replays_original_job_for_exact_path_and_body(db):
    from app.scheduling.models import Job

    async with environment(db) as (seed, client):
        path = f"/dev/v1/scenarios/{seed['scenario_run_id']}/advance"
        assert (await client.post(path, json={"steps": 1}, headers=headers())).status_code == 403
        assert (
            await client.post(path, json={"steps": 0}, headers=headers("admin"))
        ).status_code == 422
        command_headers = headers("admin")
        replies = await asyncio.gather(
            *[client.post(path, json={"steps": 1}, headers=command_headers) for _ in range(3)]
        )
        assert all(r.status_code == 202 for r in replies), [r.text for r in replies]
        receipt = replies[0].json()
        assert all(r.json() == receipt for r in replies)
        assert receipt["status"] == "READY" and receipt["merged"] is False
        async with db.session() as session, session.begin():
            job = await session.get(Job, receipt["job_run_id"])
            assert job.job_type == "advance_scenario"
            assert job.store_id == seed["store_id"]
            assert job.payload == {"scenario_run_id": seed["scenario_run_id"], "steps": 1}
            job.status = "SUCCEEDED"
        assert (
            await client.post(path, json={"steps": 1}, headers=command_headers)
        ).json() == receipt
        assert (
            await client.post(path, json={"steps": 2}, headers=command_headers)
        ).status_code == 409
        other = fresh_seed()
        await initialize(db, other)
        assert (
            await client.post(
                f"/dev/v1/scenarios/{other['scenario_run_id']}/advance",
                json={"steps": 1},
                headers=command_headers,
            )
        ).status_code == 409
        assert (
            await client.post(
                f"/dev/v1/scenarios/{uuid4()}/advance", json={"steps": 1}, headers=headers("admin")
            )
        ).status_code == 404


async def test_advance_job_retries_same_command_then_enqueues_sync_without_mutating_projection(db):
    from app.operations.client import SimulationClient
    from app.operations.jobs import make_handlers
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        before = await state(db, seed)
        response = await client.post(
            f"/dev/v1/scenarios/{seed['scenario_run_id']}/advance",
            json={"steps": 2},
            headers=headers("admin"),
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_run_id"]
        requests = []

        async def source(request):
            # The runner's claim transaction must be closed before HTTP starts.
            async with db.session() as session, session.begin():
                await session.scalar(
                    select(Job).where(Job.id == job_id).with_for_update(nowait=True)
                )
            requests.append(
                (request.url.path, request.headers["Idempotency-Key"], json.loads(request.content))
            )
            if len(requests) == 1:
                raise httpx.ReadTimeout("Committed response was lost", request=request)
            return httpx.Response(
                200,
                json={
                    "scenario_run_id": seed["scenario_run_id"],
                    "simulation_time": seed["simulation_time"],
                    "last_sequence": 3,
                },
            )

        config = settings(db, seed, simulation_token="advance-source-token-00000000001")
        sim = SimulationClient(config, transport=httpx.MockTransport(source))
        handler = make_handlers(config, client=sim)["advance_scenario"]
        runner = Runner(db, config, handlers={"advance_scenario": handler})
        assert await runner.run_once()
        async with db.session() as session, session.begin():
            job = await session.get(Job, job_id)
            assert job.status == "RETRY_WAIT"
            job.available_at = await session.scalar(select(func.clock_timestamp()))
        assert await runner.run_once()
        assert (
            requests
            == [(f"/sim/v1/runs/{seed['scenario_run_id']}/advance", job_id, {"steps": 2})] * 2
        )
        async with db.session() as session:
            assert (await session.get(Job, job_id)).status == "SUCCEEDED"
            queued = list(
                await session.scalars(
                    select(Job).where(
                        Job.store_id == seed["store_id"], Job.job_type == "sync_events"
                    )
                )
            )
            assert len(queued) == 1
            assert queued[0].payload == {"scenario_run_id": seed["scenario_run_id"]}
        assert await state(db, seed) == before


async def test_advance_rejects_response_for_another_run_before_scheduling_sync(db):
    from app.operations.client import SimulationClient
    from app.operations.jobs import make_handlers
    from app.scheduling.models import Job
    from app.scheduling.runner import Runner

    async with environment(db) as (seed, client):
        response = await client.post(
            f"/dev/v1/scenarios/{seed['scenario_run_id']}/advance",
            json={"steps": 1},
            headers=headers("admin"),
        )
        assert response.status_code == 202, response.text
        config = settings(db, seed, simulation_token="advance-source-token-00000000001")
        sim = SimulationClient(
            config,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "scenario_run_id": "wrong-run",
                        "simulation_time": seed["simulation_time"],
                        "last_sequence": 1,
                    },
                )
            ),
        )
        handler = make_handlers(config, client=sim)["advance_scenario"]
        assert await Runner(db, config, handlers={"advance_scenario": handler}).run_once()
        async with db.session() as session:
            job = await session.get(Job, response.json()["job_run_id"])
            assert (job.status, job.error_code) == ("FAILED", "INVALID_SOURCE_RESPONSE")
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.store_id == seed["store_id"], Job.job_type == "sync_events")
                )
                == 0
            )
