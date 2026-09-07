import logging

from asyncpg import PostgresError
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.core.errors import AppError


def error_response(request, status, code, message, retryable=False, details=None):
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "retryable": retryable,
                "details": details or {},
            },
        },
    )


async def application_error(request: Request, exc: AppError):
    return error_response(request, exc.status, exc.code, exc.message, exc.retryable)


async def validation_error(request: Request, exc: RequestValidationError):
    fields = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
    return error_response(
        request, 422, "VALIDATION_ERROR", "Request validation failed", details={"fields": fields}
    )


async def http_error(request: Request, exc: HTTPException):
    code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return error_response(request, exc.status_code, code, "Request cannot be served")


async def database_error(request: Request, exc: Exception):
    logging.getLogger("shopsteward").warning(
        "database_unavailable",
        extra={
            "request_id": request.state.request_id,
            "error_type": type(exc).__name__,
        },
    )
    return error_response(request, 503, "DEPENDENCY_UNAVAILABLE", "Database is unavailable", True)


async def unexpected_error(request: Request, exc: Exception):
    logging.getLogger("shopsteward").error(
        "request_failed",
        extra={
            "request_id": request.state.request_id,
            "error_type": type(exc).__name__,
        },
    )
    return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")


def install_errors(app):
    for kind, handler in [
        (AppError, application_error),
        (RequestValidationError, validation_error),
        (HTTPException, http_error),
        (SQLAlchemyError, database_error),
        (PostgresError, database_error),
        (OSError, database_error),
        (TimeoutError, database_error),
        (Exception, unexpected_error),
    ]:
        app.add_exception_handler(kind, handler)
