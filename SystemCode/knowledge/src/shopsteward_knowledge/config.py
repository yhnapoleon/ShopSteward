"""Service configuration; importing contracts never loads these settings."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KNOWLEDGE_", extra="ignore")

    database_url: str | None = None
    storage_root: Path = Path("./var/knowledge")
    opensearch_url: str | None = None
    index_prefix: str = "shopsteward-knowledge"
    service_key: SecretStr | None = None
    lease_seconds: int = Field(default=120, ge=10, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=20)
    max_total_attempts: int = Field(default=15, ge=1, le=100)
    poll_seconds: float = Field(default=1, ge=0.1, le=60)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1, le=20 * 1024 * 1024)
    embedding_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1, le=8192)
    embedding_provider: str = "http-openai-compatible"
    embedding_revision: str | None = None
    embedding_query_instruction: str = ""
    embedding_document_instruction: str = ""
    embedding_normalize: bool = True
    embedding_max_input_chars: int = Field(default=12000, ge=1, le=100000)
    embedding_deadline_ms: int = Field(default=8000, ge=1, le=60000)
    rerank_url: str | None = None
    rerank_api_key: SecretStr | None = None
    rerank_model: str | None = None

    @field_validator(
        "embedding_url",
        "embedding_api_key",
        "embedding_model",
        "embedding_dimensions",
        "embedding_revision",
        "rerank_url",
        "rerank_api_key",
        "rerank_model",
        mode="before",
    )
    @classmethod
    def blank_provider_option(cls, value):
        # Compose interpolates absent optional settings as empty strings, including integers.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def complete_embedding_configuration(self):
        if self.max_total_attempts < self.max_attempts:
            raise ValueError("max_total_attempts must cover the initial attempt window")
        values = [
            self.embedding_url,
            self.embedding_api_key,
            self.embedding_model,
            self.embedding_dimensions,
        ]
        if any(value is not None for value in values) and not all(values):
            raise ValueError("embedding requires complete explicit URL/API_KEY/MODEL/DIMENSIONS")
        if self.embedding_api_key and not self.embedding_api_key.get_secret_value().strip():
            raise ValueError("embedding requires complete explicit API_KEY")
        return self

    @model_validator(mode="after")
    def complete_rerank_configuration(self):
        values = [self.rerank_url, self.rerank_api_key, self.rerank_model]
        if any(value is not None for value in values) and not all(values):
            raise ValueError("rerank requires complete explicit URL/API_KEY/MODEL")
        if self.rerank_api_key and not self.rerank_api_key.get_secret_value().strip():
            raise ValueError("rerank requires complete explicit API_KEY")
        return self

    def embedding_profile(self):
        if self.embedding_url is None:
            return None
        from .contracts import EmbeddingProfile

        return EmbeddingProfile(
            provider=self.embedding_provider,
            model=self.embedding_model,
            revision=self.embedding_revision,
            dimensions=self.embedding_dimensions,
            query_instruction=self.embedding_query_instruction,
            document_instruction=self.embedding_document_instruction,
            normalize=self.embedding_normalize,
            max_input_chars=self.embedding_max_input_chars,
        ).model_dump()

    def enabled_profiles(self):
        return {"lexical-v1", "hybrid-v1"} if self.embedding_profile() else {"lexical-v1"}

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value):
        if not value:
            return None
        parsed = make_url(value)
        if parsed.get_backend_name() != "postgresql":
            raise ValueError("knowledge requires PostgreSQL; SQLite is not supported")
        return parsed.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)

    @field_validator("service_key")
    @classmethod
    def nonempty_key(cls, value):
        if value is not None and not value.get_secret_value().strip():
            return None
        return value


def create_embedding(settings, client):
    if settings.embedding_profile() is None:
        return None
    from .providers.embedding import HttpEmbedding

    return HttpEmbedding(
        client, settings.embedding_url, settings.embedding_api_key.get_secret_value()
    )


def create_reranker(settings, client):
    if settings.rerank_url is None:
        return None
    from .providers.rerank import HttpRerank

    return HttpRerank(
        client,
        settings.rerank_url,
        settings.rerank_api_key.get_secret_value(),
        settings.rerank_model,
    )
