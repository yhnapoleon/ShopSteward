from contextlib import asynccontextmanager

import httpx

from app.core.errors import AppError


@asynccontextmanager
async def connect(settings):
    if not settings.forecast_v6_enabled or not settings.forecast_v6_token:
        raise AppError(
            503, "FORECAST_UNAVAILABLE", "v6 model service is disabled or not configured"
        )
    async with httpx.AsyncClient(
        base_url=settings.forecast_v6_url.rstrip("/"),
        headers={"Authorization": "Bearer " + settings.forecast_v6_token.get_secret_value()},
        timeout=settings.forecast_v6_timeout_seconds,
        follow_redirects=False,
    ) as client:
        yield client


async def json_request(client, method, path, **kwargs):
    try:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Model response must be an object")
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(
            503,
            "FORECAST_UNAVAILABLE",
            "v6 model service could not supply valid evidence",
            retryable=True,
        ) from exc
