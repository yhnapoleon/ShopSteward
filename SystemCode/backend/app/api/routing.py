import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas import Error

errors = {code: {"model": Error} for code in (401, 403, 404, 409, 422, 500, 503)}


async def remember_language(request: Request):
    """A user's command remembers the interface language for model text written later.

    Reads only headers, so it adds nothing to the OpenAPI operation; the endpoint's
    own dependencies still decide authentication.
    """
    from app.agent_bridge.language import remember, requested
    from app.api.dependencies import bearer, require_user
    from app.core.errors import AppError

    language = requested(request)
    if language is None or request.method == "GET":
        return
    try:
        principal = require_user(request, await bearer(request))
    except AppError:
        return
    try:
        async with request.app.state.db.session() as session, session.begin():
            await remember(session, principal.principal_id, language)
    except SQLAlchemyError:
        # A missed preference must not fail the command; the last remembered one stays.
        logging.getLogger("shopsteward").warning("ui_language_not_saved")


class B0Router(APIRouter):
    """B0 routes carry implementation metadata, including after router inclusion."""

    def __init__(self, *args, dependencies=None, **kwargs):
        super().__init__(
            *args, dependencies=[Depends(remember_language), *(dependencies or [])], **kwargs
        )

    def add_api_route(self, path, endpoint, *, openapi_extra=None, **kwargs):
        metadata = {"x-phase": "B0", "x-implementation-status": "implemented"}
        super().add_api_route(
            path, endpoint, openapi_extra=metadata | (openapi_extra or {}), **kwargs
        )
