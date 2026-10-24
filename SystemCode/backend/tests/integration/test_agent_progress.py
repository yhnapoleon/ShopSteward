import asyncio
import json
import socket

import httpx
import pytest
from sqlalchemy import select
from test_agent_runs import clean_agent, setup_agent  # noqa: F401
from test_missions import headers

pytestmark = pytest.mark.integration


async def queued(client, mission, content="读取经营数据"):
    c = (
        await client.post(
            f"/api/v1/missions/{mission['id']}/conversations", json={}, headers=headers()
        )
    ).json()
    run = (
        await client.post(
            f"/api/v1/conversations/{c['id']}/messages",
            json={"content": content},
            headers=headers(),
        )
    ).json()
    return run["agent_run_id"]


async def test_start_visible_before_completion_and_replay_is_unique(db, monkeypatch):
    from app.agent_bridge import tools
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    entered, release = asyncio.Event(), asyncio.Event()
    original = tools.execute_tool

    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(tools, "execute_tool", slow)
    results = []

    async def execute(context):
        body = {"run_id": context["run_id"], "invocation_id": "read-1", "arguments": {}}
        auth = {"Authorization": "Bearer " + context["token"]}
        for _ in range(2):
            r = await client.post("/internal/v1/agent-tools/get_dashboard", json=body, headers=auth)
            assert r.status_code == 200, r.text
            results.append(r.json())
        return {"status": "SUCCEEDED", "content": "已读取", "references": []}

    async with client:
        rid = await queued(client, mission)
        worker = asyncio.create_task(
            Runner(
                db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
            ).run_once()
        )
        try:
            await asyncio.wait_for(entered.wait(), 5)
            page = (await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers())).json()
            assert [e["type"] for e in page["events"]] == [
                "run.queued",
                "run.started",
                "tool.started",
            ]
            snapshot = (await client.get(f"/api/v1/agent-runs/{rid}", headers=headers())).json()
            assert snapshot["activity"][0]["status"] == "RUNNING"
            assert snapshot["tools"] == []
            assert snapshot["progress_seq"] == page["latest_seq"]
        finally:
            release.set()
        await asyncio.wait_for(worker, 5)
        page = (await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers())).json()
        types = [e["type"] for e in page["events"]]
        assert types == [
            "run.queued",
            "run.started",
            "tool.started",
            "tool.completed",
            "run.completed",
        ]
        assert [e["seq"] for e in page["events"]] == list(range(1, 6))
        assert results[0] == results[1]
        tool = page["events"][3]["payload"]["activity"]
        assert tool["duration_ms"] >= 0 and tool["finished_at"]
        assert "arguments" not in json.dumps(page) and "token" not in json.dumps(page)
        first = (
            await client.get(f"/api/v1/agent-runs/{rid}/events?limit=2", headers=headers())
        ).json()
        rest = (
            await client.get(
                f"/api/v1/agent-runs/{rid}/events?after_seq={first['next_after_seq']}",
                headers=headers(),
            )
        ).json()
        assert first["has_more"] and [e["seq"] for e in rest["events"]] == [3, 4, 5]
        assert (
            await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers("viewer"))
        ).status_code == 404
        assert (
            await client.get(f"/api/v1/agent-runs/{rid}/events?after_seq=999", headers=headers())
        ).status_code == 409
    await app.state.db.dispose()


async def test_rollback_never_emits_completed_or_saves_memory(db, monkeypatch):
    from app.agent_bridge import progress
    from app.agent_bridge.jobs import make_handlers
    from app.agent_bridge.models import KnowledgeScope, ToolInvocation
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    original = progress.complete_tool

    async def broken(*args, **kwargs):
        assert args[3]["ok"] is True
        await original(*args, **kwargs)
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(progress, "complete_tool", broken)

    async def execute(context):
        try:
            await client.post(
                "/internal/v1/agent-tools/memory_edit",
                json={
                    "run_id": context["run_id"],
                    "invocation_id": "rolled-back",
                    "arguments": {
                        "kind": "USER",
                        "operation": "add",
                        "content": "先说现金风险",
                        "expected_version": 0,
                    },
                },
                headers={"Authorization": "Bearer " + context["token"]},
            )
        except RuntimeError:
            pass
        return {"status": "SUCCEEDED", "content": "读取未完成", "references": []}

    async with client:
        rid = await queued(client, mission, "请长期记住：先说现金风险")
        await Runner(
            db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
        ).run_once()
        page = (await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers())).json()
        assert "tool.completed" not in [e["type"] for e in page["events"]]
        assert "tool.interrupted" in [e["type"] for e in page["events"]]
        async with db.session() as session:
            assert await session.get(ToolInvocation, (rid, "rolled-back")) is None
            assert (
                await session.scalar(
                    select(KnowledgeScope).where(KnowledgeScope.store_id == mission["store_id"])
                )
                is None
            )
    await app.state.db.dispose()


async def test_real_http_stream_delivers_start_before_tool_returns(db, monkeypatch):
    import uvicorn

    from app.agent_bridge import tools
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, setup_client, mission = await setup_agent(db)
    await setup_client.aclose()
    release = asyncio.Event()
    original = tools.execute_tool

    async def slow(*args, **kwargs):
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(tools, "execute_tool", slow)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    address = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    worker = None
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        async with httpx.AsyncClient(base_url=address, timeout=8) as client:

            async def execute(context):
                r = await client.post(
                    "/internal/v1/agent-tools/get_dashboard",
                    json={
                        "run_id": context["run_id"],
                        "invocation_id": "live-read",
                        "arguments": {},
                    },
                    headers={"Authorization": "Bearer " + context["token"]},
                )
                assert r.status_code == 200, r.text
                return {"status": "SUCCEEDED", "content": "已读取", "references": []}

            rid = await queued(client, mission)
            worker = asyncio.create_task(
                Runner(
                    db,
                    app.state.settings,
                    handlers=make_handlers(app.state.settings, executor=execute),
                ).run_once()
            )
            received = []
            async with client.stream(
                "GET", f"/api/v1/agent-runs/{rid}/events/stream", headers=headers()
            ) as response:
                assert response.headers["content-type"].startswith("text/event-stream")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if "type" not in data:
                        continue
                    received.append(data["type"])
                    if data["type"] == "tool.started":
                        assert not worker.done()
                        release.set()
            await worker
            assert (
                "tool.started" in received
                and "tool.completed" in received
                and received[-1] == "run.completed"
            )
            # Replay resumes after the cursor and does not replay earlier starts.
            async with client.stream(
                "GET",
                f"/api/v1/agent-runs/{rid}/events/stream",
                headers={**headers(), "Last-Event-ID": "3"},
            ) as response:
                replay = await response.aread()
                assert b"tool.started" not in replay and b"tool.completed" in replay
    finally:
        release.set()
        if worker and not worker.done():
            await worker
        server.should_exit = True
        await serving
        sock.close()
    await app.state.db.dispose()


async def test_cancel_after_admission_prevents_tool_execution(db, monkeypatch):
    from app.agent_bridge import progress, tools
    from app.agent_bridge.jobs import make_handlers
    from app.scheduling.runner import Runner

    app, client, mission = await setup_agent(db)
    entered, release = asyncio.Event(), asyncio.Event()
    original = progress.start_tool
    calls = []

    async def admitted(*args):
        await original(*args)
        entered.set()
        await release.wait()

    async def should_not_execute(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Cancelled tool reached execution")

    monkeypatch.setattr(progress, "start_tool", admitted)
    monkeypatch.setattr(tools, "execute_tool", should_not_execute)

    async def execute(context):
        response = await client.post(
            "/internal/v1/agent-tools/get_dashboard",
            json={"run_id": context["run_id"], "invocation_id": "cancel-me", "arguments": {}},
            headers={"Authorization": "Bearer " + context["token"]},
        )
        assert response.status_code == 401
        return {"status": "SUCCEEDED", "content": "stopped", "references": []}

    async with client:
        rid = await queued(client, mission)
        worker = asyncio.create_task(
            Runner(
                db, app.state.settings, handlers=make_handlers(app.state.settings, executor=execute)
            ).run_once()
        )
        try:
            await asyncio.wait_for(entered.wait(), 5)
            response = await client.post(
                f"/api/v1/agent-runs/{rid}/cancel", json={}, headers=headers()
            )
            assert response.json()["status"] == "CANCELLED"
        finally:
            release.set()
        await asyncio.wait_for(worker, 5)
        snapshot = (await client.get(f"/api/v1/agent-runs/{rid}", headers=headers())).json()
        assert snapshot["activity"][0]["status"] == "INTERRUPTED"
        assert snapshot["tools"] == [] and calls == []
        events = (await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers())).json()[
            "events"
        ]
        assert [e["type"] for e in events][-2:] == ["tool.interrupted", "run.cancelled"]
    await app.state.db.dispose()


async def test_open_stream_rechecks_revoked_identity(db):
    import uvicorn

    app, setup_client, mission = await setup_agent(db)
    await setup_client.aclose()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=url, timeout=5) as client:
            rid = await queued(client, mission)
            path = f"/api/v1/agent-runs/{rid}/events/stream"
            assert (await client.get(path, headers=headers("viewer"))).status_code == 404
            assert (
                await client.get(path, headers={**headers(), "Last-Event-ID": "-1"})
            ).status_code == 422
            revoked = False
            async with client.stream("GET", path, headers=headers()) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and not revoked:
                        token = headers()["Authorization"].split(" ", 1)[1]
                        app.state.settings.auth_tokens = [
                            g
                            for g in app.state.settings.auth_tokens
                            if g.token.get_secret_value() != token
                        ]
                        revoked = True
                    if line == "event: access_revoked":
                        break
                else:
                    raise AssertionError("Stream did not stop after revocation")
            assert revoked
            assert (
                await client.get(f"/api/v1/agent-runs/{rid}/events", headers=headers())
            ).status_code == 401
    finally:
        server.should_exit = True
        await serving
        sock.close()
    await app.state.db.dispose()
