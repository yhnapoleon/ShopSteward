import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import TokenGrant
from app.core.errors import AppError

bearer = HTTPBearer(scheme_name="UserBearer", auto_error=False)


def require_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> TokenGrant:
    if credentials is not None:
        for grant in request.app.state.settings.auth_tokens:
            if secrets.compare_digest(
                credentials.credentials.encode("utf-8"),
                grant.token.get_secret_value().encode("utf-8"),
            ):
                if grant.kind != "user":
                    raise AppError(403, "FORBIDDEN", "A user identity is required")
                return grant
    raise AppError(401, "UNAUTHENTICATED", "A valid bearer credential is required")


User = Annotated[TokenGrant, Depends(require_user)]


def require_admin(principal: User) -> TokenGrant:
    if "admin" not in principal.roles:
        raise AppError(403, "FORBIDDEN", "Admin permission is required")
    return principal


Admin = Annotated[TokenGrant, Depends(require_admin)]

service_bearer = HTTPBearer(scheme_name="ServiceBearer", auto_error=False)


def require_service(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(service_bearer)],
) -> TokenGrant:
    if credentials is not None:
        for grant in request.app.state.settings.auth_tokens:
            if secrets.compare_digest(
                credentials.credentials.encode(), grant.token.get_secret_value().encode()
            ):
                if grant.kind != "service":
                    raise AppError(403, "FORBIDDEN", "A service identity is required")
                return grant
    raise AppError(401, "UNAUTHENTICATED", "A valid service credential is required")


Service = Annotated[TokenGrant, Depends(require_service)]


def authorize_store(principal, store_id):
    if "admin" not in principal.roles and (
        not principal.roles or store_id not in principal.store_ids
    ):
        raise AppError(404, "RESOURCE_NOT_FOUND", "Store is not visible or does not exist")
