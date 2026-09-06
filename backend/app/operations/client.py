import json
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.core.errors import AppError
from app.operations.schemas import EventPage, ScenarioRun


class SimulationClient:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    async def request(
        self, method, path, *, allow_missing=False, preserve_conflict=False, **kwargs
    ):
        if self.settings.simulation_token is None:
            raise AppError(503, "DEPENDENCY_UNAVAILABLE", "Simulation credential is not configured")
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.simulation_base_url,
                timeout=httpx.Timeout(10, connect=3),
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
                headers={
                    "Authorization": "Bearer " + self.settings.simulation_token.get_secret_value()
                },
            ) as client:
                response = await client.request(method, path, **kwargs)
            if allow_missing and response.status_code == 404:
                return None
            if preserve_conflict and (response.is_success or response.status_code == 409):
                try:
                    data = response.json()
                    if data is None:
                        raise ValueError("JSON null is not an absent purchase")
                    json.dumps(data, allow_nan=False)
                    return data
                except ValueError:
                    return {"http_status": response.status_code, "raw_body": response.text[:4096]}
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(
                503,
                "SIMULATION_UNAVAILABLE",
                "Simulator request could not be completed",
                retryable=True,
            ) from exc

    async def create(self, key, payload):
        data = await self.request(
            "POST", "/sim/v1/runs", json=payload, headers={"Idempotency-Key": key}
        )
        return self.validate(ScenarioRun, data)

    async def events(self, run_id, after):
        data = await self.request(
            "GET",
            f"/sim/v1/runs/{quote(run_id, safe='')}/events",
            params={"after_sequence": after, "limit": 100},
        )
        return self.validate(EventPage, data)

    async def advance(self, run_id, key, payload):
        from app.execution.schemas import AdvanceResult

        data = await self.request(
            "POST",
            f"/sim/v1/runs/{quote(run_id, safe='')}/advance",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        return self.validate(AdvanceResult, data)

    async def purchase(self, action_id, payload):
        return await self.request(
            "POST",
            "/sim/v1/purchases",
            json=payload,
            headers={"Idempotency-Key": action_id},
            preserve_conflict=True,
        )

    async def get_purchase(self, action_id):
        return await self.request(
            "GET",
            "/sim/v1/purchases/" + quote(action_id, safe=""),
            allow_missing=True,
            preserve_conflict=True,
        )

    @staticmethod
    def validate(model, value):
        try:
            return model.model_validate(value)
        except ValidationError as exc:
            raise AppError(
                503, "INVALID_SOURCE_RESPONSE", "Simulator response violated the contract"
            ) from exc
