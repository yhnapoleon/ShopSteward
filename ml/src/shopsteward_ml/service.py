"""Token-protected local HTTP boundary for the portable v6 runtime."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException

from .runtime import ForecastRuntime
from .schemas import PredictRequest


def create_app(*, runtime: ForecastRuntime | None = None, token: str | None = None):
    secret = token if token is not None else os.environ.get("ML_SERVICE_TOKEN", "")
    if not secret:
        raise RuntimeError("ML_SERVICE_TOKEN_REQUIRED")
    loaded = runtime or ForecastRuntime(
        Path(os.environ.get("ML_V6_BUNDLE", "var/forecast-v6/bundle"))
    )

    def authorize(authorization: str | None = Header(default=None)):
        if authorization is None or not hmac.compare_digest(
            authorization.encode(), ("Bearer " + secret).encode()
        ):
            raise HTTPException(
                status_code=401, detail="UNAUTHORIZED", headers={"WWW-Authenticate": "Bearer"}
            )

    app = FastAPI(
        title="ShopSteward v6 Forecast",
        version="6.0.0",
        dependencies=[Depends(authorize)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = loaded

    @app.get("/health/ready")
    def ready():
        return {
            "ready": True,
            "model_version": loaded.manifest["model_version"],
            "components": list(loaded.models),
        }

    @app.get("/v1/model")
    def model():
        return loaded.descriptor()

    @app.get("/v1/demo-history/{series_id}")
    def demo(series_id: str):
        try:
            return loaded.demo_history(series_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/predict")
    def predict(request: PredictRequest):
        try:
            return loaded.predict(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
