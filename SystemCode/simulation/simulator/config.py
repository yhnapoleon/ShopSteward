from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8-sig", extra="ignore"
    )
    sim_database_url: SecretStr | None = None
    sim_service_token: SecretStr | None = Field(default=None, min_length=24)
    sim_console_enabled: bool = False
    sim_backend_base_url: str = "http://127.0.0.1:8000"
    sim_backend_token: SecretStr | None = Field(default=None, min_length=24)

    @field_validator("sim_backend_base_url")
    @classmethod
    def local_backend(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Console backend must be a fixed local HTTP origin")
        return value.rstrip("/")

    @field_validator("sim_database_url", mode="before")
    @classmethod
    def postgres_only(cls, value):
        if value is None or value == "":
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw.startswith("postgresql+asyncpg://"):
            raise ValueError("SIM_DATABASE_URL must use postgresql+asyncpg")
        return value
