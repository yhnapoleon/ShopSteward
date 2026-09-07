from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TokenGrant(BaseModel):
    token: SecretStr = Field(min_length=24)
    principal_id: str = Field(min_length=1, max_length=128)
    kind: Literal["user", "service"] = "user"
    roles: list[Literal["viewer", "operator", "approver", "admin"]] = Field(default_factory=list)
    store_ids: list[str] = Field(default_factory=list)
    scenario_run_ids: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8-sig", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr | None = None
    auth_tokens: list[TokenGrant] = Field(default_factory=list, repr=False)
    docs_enabled: bool | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    worker_concurrency: int = Field(default=4, ge=1, le=32)
    job_lease_seconds: int = Field(default=30, ge=2, le=3600)
    job_heartbeat_seconds: int = Field(default=10, ge=1)
    worker_poll_seconds: float = Field(default=1, gt=0, le=60)
    worker_shutdown_seconds: float = Field(default=10, gt=0, le=60)
    job_timeout_seconds: float = Field(default=120, gt=0, le=3600)
    simulation_base_url: str = "http://127.0.0.1:8001"
    simulation_token: SecretStr | None = Field(default=None, min_length=24)
    source_stale_seconds: int = Field(default=30, ge=1, le=3600)
    plan_ttl_seconds: int = Field(default=900, ge=1, le=86400)
    fixed_forecast_ttl_seconds: int = Field(default=3600, ge=1, le=86400)
    # Relative paths resolve against the API process working directory.
    knowledge_storage_root: str = "var/knowledge"
    agent_enabled: bool = False
    agent_base_url: str = "https://api.openai.com/v1"
    agent_model: str = "gpt-4.1-mini"
    agent_api_key_file: str | None = Field(default=None, repr=False)
    agent_backend_url: str = "http://127.0.0.1:8000"
    agent_worker_concurrency: int = Field(default=1, ge=1, le=8)

    @field_validator("database_url", mode="before")
    @classmethod
    def postgres_only(cls, value):
        if value is None or value == "":
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.job_lease_seconds <= self.job_heartbeat_seconds:
            raise ValueError("JOB_LEASE_SECONDS must exceed JOB_HEARTBEAT_SECONDS")
        tokens = [grant.token.get_secret_value() for grant in self.auth_tokens]
        if len(tokens) != len(set(tokens)):
            raise ValueError("AUTH_TOKENS contains duplicate credentials")
        return self

    @property
    def show_docs(self) -> bool:
        return self.docs_enabled if self.docs_enabled is not None else self.app_env != "production"
