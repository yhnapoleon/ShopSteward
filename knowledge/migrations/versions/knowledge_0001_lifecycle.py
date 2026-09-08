"""Initial independent knowledge lifecycle schema (frozen PostgreSQL DDL)."""

from alembic import op

revision = "knowledge_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE knowledge_originals (
            version_id VARCHAR(128) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            storage_key VARCHAR(512) NOT NULL,
            size_bytes INTEGER NOT NULL,
            mime VARCHAR(128) NOT NULL,
            PRIMARY KEY (version_id),
            CHECK (size_bytes > 0),
            UNIQUE (storage_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_projections (
            version_id VARCHAR(128) NOT NULL,
            document_id VARCHAR(128) NOT NULL,
            store_id VARCHAR(128) NOT NULL,
            metadata_revision INTEGER NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (version_id),
            CHECK (metadata_revision >= 1)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_projections_store_id
        ON knowledge_projections (store_id)
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_index_generations (
            id VARCHAR(128) NOT NULL,
            version_id VARCHAR(128) NOT NULL,
            profile_id VARCHAR(128) NOT NULL,
            metadata_revision INTEGER NOT NULL,
            state VARCHAR(16) NOT NULL,
            chunk_count INTEGER NOT NULL,
            manifest_hash VARCHAR(64),
            manifest JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            ready_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            CHECK (state IN ('BUILDING', 'READY', 'FAILED')),
            CHECK (chunk_count >= 0),
            CHECK (state != 'READY' OR (chunk_count > 0 AND manifest_hash IS NOT NULL)),
            FOREIGN KEY(version_id) REFERENCES knowledge_originals (version_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_generation_version
        ON knowledge_index_generations (version_id, metadata_revision)
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
            generation_id VARCHAR(128) NOT NULL,
            chunk_id VARCHAR(128) NOT NULL,
            version_id VARCHAR(128) NOT NULL,
            store_id VARCHAR(128) NOT NULL,
            metadata_revision INTEGER NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL,
            PRIMARY KEY (generation_id, chunk_id),
            FOREIGN KEY(generation_id) REFERENCES knowledge_index_generations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_chunks_scope
        ON knowledge_chunks (store_id, version_id)
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_jobs (
            id VARCHAR(128) NOT NULL,
            idempotency_key VARCHAR(200) NOT NULL,
            payload_hash VARCHAR(64) NOT NULL,
            request JSONB NOT NULL,
            generation_id VARCHAR(128) NOT NULL,
            state VARCHAR(16) NOT NULL,
            attempt INTEGER NOT NULL,
            next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            lease_owner VARCHAR(128),
            lease_token VARCHAR(128),
            lease_until TIMESTAMP WITH TIME ZONE,
            error TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (idempotency_key),
            CHECK (state IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED')),
            CHECK (attempt >= 0),
            FOREIGN KEY(generation_id) REFERENCES knowledge_index_generations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_jobs_claim
        ON knowledge_jobs (state, next_attempt_at, lease_until)
        """
    )
    op.execute(
        """
        CREATE TABLE knowledge_relations (
            id VARCHAR(128) NOT NULL,
            generation_id VARCHAR(128) NOT NULL,
            version_id VARCHAR(128) NOT NULL,
            store_id VARCHAR(128) NOT NULL,
            metadata_revision INTEGER NOT NULL,
            subject VARCHAR(256) NOT NULL,
            predicate VARCHAR(128) NOT NULL,
            object VARCHAR(256) NOT NULL,
            confirmed BOOLEAN NOT NULL,
            conditions JSONB NOT NULL,
            evidence_chunk_ids JSONB NOT NULL,
            valid_from TIMESTAMP WITH TIME ZONE,
            valid_until TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
            FOREIGN KEY(generation_id) REFERENCES knowledge_index_generations (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_relations_scope
        ON knowledge_relations (store_id, generation_id, subject, predicate)
        """
    )
    op.execute(
        """
        CREATE FUNCTION knowledge_original_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'knowledge original is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_original_immutable
        BEFORE UPDATE OR DELETE ON knowledge_originals
        FOR EACH ROW EXECUTE FUNCTION knowledge_original_immutable()
        """
    )


def downgrade():
    op.execute("DROP TRIGGER knowledge_original_immutable ON knowledge_originals")
    op.execute("DROP FUNCTION knowledge_original_immutable()")
    op.drop_table("knowledge_relations")
    op.drop_table("knowledge_jobs")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_index_generations")
    op.drop_table("knowledge_projections")
    op.drop_table("knowledge_originals")
