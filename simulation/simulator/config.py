from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8-sig", extra="ignore"
    )
    sim_database_url: SecretStr | None = None
    sim_service_token: SecretStr | None = Field(default=None, min_length=24)

    @field_validator("sim_database_url", mode="before")
    @classmethod
    def postgres_only(cls, value):
        if value is None or value == "":
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw.startswith("postgresql+asyncpg://"):
            raise ValueError("SIM_DATABASE_URL must use postgresql+asyncpg")
        return value
