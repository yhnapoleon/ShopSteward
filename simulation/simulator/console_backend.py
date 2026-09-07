"""Fixed local backend HTTP operations; never read backend tables or proxy arbitrary paths."""

import asyncio
from urllib.parse import quote

import httpx
from fastapi import HTTPException


class BackendBridge:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    @property
    def configured(self):
        return self.settings.sim_backend_token is not None

    async def request(self, method, path, **kwargs):
        if not self.configured:
            raise HTTPException(503, "BACKEND_NOT_CONFIGURED")
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.sim_backend_base_url,
                headers={
                    "Authorization": "Bearer " + self.settings.sim_backend_token.get_secret_value()
                },
                timeout=httpx.Timeout(5, connect=2),
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                r = await client.request(method, path, **kwargs)
            value = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, "BACKEND_UNAVAILABLE") from exc
        if not r.is_success:
            code = (
                value.get("error", {}).get("code", "BACKEND_REQUEST_FAILED")
                if isinstance(value, dict)
                else "BACKEND_REQUEST_FAILED"
            )
            raise HTTPException(r.status_code if 400 <= r.status_code < 600 else 502, code)
        return value

    async def health(self):
        if not self.configured:
            return "not_configured"
        try:
            await self.request("GET", "/health/ready")
            return "ready"
        except HTTPException:
            return "unavailable"

    async def create(self, body, key):
        return await self.request(
            "POST",
            "/dev/v1/scenarios",
            json=body.model_dump(exclude_none=True),
            headers={"Idempotency-Key": key},
        )

    async def job(self, job_id):
        return await self.request("GET", "/api/v1/job-runs/" + quote(job_id, safe=""))

    async def observe(self, store_id):
        if not self.configured:
            return {"status": "not_configured"}
        try:
            dashboard = await self.request(
                "GET", "/api/v1/dashboard", params={"store_id": store_id}
            )
            sales, missions, alerts = await asyncio.gather(
                self.request("GET", "/api/v1/sales", params={"store_id": store_id, "limit": 1}),
                self.request("GET", "/api/v1/missions", params={"store_id": store_id, "limit": 10}),
                self.request("GET", "/api/v1/alerts", params={"store_id": store_id, "limit": 10}),
            )
            plans = await asyncio.gather(
                *[
                    self.request("GET", "/api/v1/plans/" + quote(m["current_plan_id"], safe=""))
                    for m in missions["items"]
                    if m.get("current_plan_id")
                ]
            )
            return {
                "status": "ok",
                "dashboard": dashboard,
                "source_sequence": sales["context"]["source_sequence"],
                "missions": missions["items"],
                "plans": list(plans),
                "alerts": alerts["items"],
            }
        except HTTPException as exc:
            return {
                "status": "not_imported" if exc.status_code == 404 else "unavailable",
                "error_code": exc.detail,
            }
