from fastapi import APIRouter

from app.api.schemas import Error

errors = {code: {"model": Error} for code in (401, 403, 404, 409, 422, 500, 503)}


class B0Router(APIRouter):
    """B0 routes carry implementation metadata, including after router inclusion."""

    def add_api_route(self, path, endpoint, *, openapi_extra=None, **kwargs):
        metadata = {"x-phase": "B0", "x-implementation-status": "implemented"}
        super().add_api_route(
            path, endpoint, openapi_extra=metadata | (openapi_extra or {}), **kwargs
        )
