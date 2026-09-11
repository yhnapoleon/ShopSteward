import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agent_bridge.router import router as agent_router
from app.agent_bridge.tools import router as agent_tool_router
from app.alerts.router import router as alerts_router
from app.api.errors import install_errors
from app.api.router import router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.execution.router import router as execution_router
from app.forecast_v6.router import router as forecast_v6_router
from app.knowledge.router import router as knowledge_router
from app.missions.router import router as missions_router
from app.operations.router import dev_router
from app.operations.router import router as operations_router
from app.planning.router import router as planning_router
from app.reporting.read_router import router as read_router
from app.reporting.router import router as reporting_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await app.state.db.dispose()

    app = FastAPI(
        title="ShopSteward Backend API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.show_docs else None,
        openapi_url="/openapi.json" if settings.show_docs else None,
        redoc_url=None,
    )
    app.include_router(alerts_router)
    app.include_router(agent_router)
    app.include_router(agent_tool_router)
    app.include_router(reporting_router)
    app.include_router(read_router)
    app.include_router(execution_router)
    app.include_router(planning_router)
    app.include_router(forecast_v6_router)
    app.state.settings = settings
    url = settings.database_url.get_secret_value() if settings.database_url else None
    app.state.db = Database(url)
    install_errors(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        # Always generate a server-owned ID; never log raw auth headers/query/body.
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logging.getLogger("shopsteward").info(
            "http_request",
            extra={
                "request_id": request.state.request_id,
                "status_code": response.status_code,
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(router)
    app.include_router(operations_router)
    app.include_router(missions_router)
    app.include_router(knowledge_router)
    if settings.app_env != "production":
        app.include_router(dev_router)
    return app


app = create_app()
