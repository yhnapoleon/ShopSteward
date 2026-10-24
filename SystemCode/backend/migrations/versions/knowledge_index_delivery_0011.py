"""Durable knowledge transport, immutable provenance and authoritative publication."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_knowledge_delivery"
down_revision = "0010_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_documents",
        sa.Column("evidence_revision", sa.BigInteger(), nullable=False, server_default="1"),
    )
    op.execute("UPDATE knowledge_documents SET evidence_revision = metadata_version")
    op.create_check_constraint("evidence_revision", "knowledge_documents", "evidence_revision >= 1")
    op.add_column(
        "knowledge_documents",
        sa.Column("publication_revision", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.drop_constraint(
        op.f("ck_knowledge_documents_indexing_status"), "knowledge_documents", type_="check"
    )
    op.create_check_constraint(
        "indexing_status",
        "knowledge_documents",
        "indexing_status IN ('NOT_INDEXED','QUEUED','INDEXING','READY','PARTIAL','FAILED')",
    )
    op.create_table(
        "knowledge_version_provenance",
        sa.Column(
            "version_id", sa.String(128), sa.ForeignKey("knowledge_versions.id"), primary_key=True
        ),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_family_id", sa.String(128)),
        sa.Column("scenario_family_id", sa.String(128)),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("publisher", sa.String(300)),
        sa.Column("jurisdiction", sa.String(100)),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("original_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )
    op.execute("""INSERT INTO knowledge_version_provenance
        (version_id, source_kind, synthetic, original_sha256)
        SELECT id, 'document', false, content_sha256 FROM knowledge_versions""")
    op.execute("""CREATE FUNCTION knowledge_provenance_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'Knowledge provenance is immutable' USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM knowledge_versions WHERE id = NEW.version_id
                AND content_sha256 = NEW.original_sha256) THEN
                RAISE EXCEPTION 'Provenance original hash mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER knowledge_provenance_guard BEFORE INSERT OR UPDATE OR DELETE
        ON knowledge_version_provenance FOR EACH ROW
        EXECUTE FUNCTION knowledge_provenance_guard()""")
    op.create_table(
        "knowledge_delivery_outbox",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("version_id", sa.String(128), nullable=False),
        sa.Column("metadata_revision", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt", sa.BigInteger(), nullable=False),
        sa.Column("retry_count", sa.BigInteger(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_token", sa.String(128)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("job_id", sa.String(128)),
        sa.Column("remote_retry_key", sa.String(64)),
        sa.Column("generation_id", sa.String(128)),
        sa.Column("manifest_hash", sa.String(64)),
        sa.Column("error", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "version_id"],
            ["knowledge_versions.document_id", "knowledge_versions.id"],
        ),
        sa.CheckConstraint("operation IN ('ingest','projection')", name="operation"),
        sa.CheckConstraint(
            "state IN ('PENDING','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED')", name="state"
        ),
        sa.CheckConstraint(
            "metadata_revision >= 1 AND attempt >= 0 AND retry_count >= 0", name="counters"
        ),
        sa.CheckConstraint(
            "(state = 'RUNNING') = (lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL AND lease_owner IS NOT NULL)",
            name="lease",
        ),
    )
    op.create_index(
        "ix_knowledge_delivery_claim", "knowledge_delivery_outbox", ["state", "next_attempt_at"]
    )
    op.create_table(
        "knowledge_publications",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("version_id", sa.String(128), nullable=False),
        sa.Column("generation_id", sa.String(128), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("metadata_revision", sa.BigInteger(), nullable=False),
        sa.Column("publication_revision", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id", "version_id"],
            ["knowledge_versions.document_id", "knowledge_versions.id"],
        ),
        sa.UniqueConstraint(
            "document_id", "publication_revision", name="uq_knowledge_publication_revision"
        ),
        sa.CheckConstraint(
            "metadata_revision >= 1 AND publication_revision >= 1", name="revisions"
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from", name="validity"
        ),
        sa.CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="manifest"),
    )
    op.create_index(
        "ix_knowledge_publications_current", "knowledge_publications", ["document_id", "active"]
    )


def downgrade():
    op.drop_table("knowledge_publications")
    op.drop_table("knowledge_delivery_outbox")
    op.drop_table("knowledge_version_provenance")
    op.execute("DROP FUNCTION knowledge_provenance_guard()")
    op.drop_constraint(
        op.f("ck_knowledge_documents_indexing_status"), "knowledge_documents", type_="check"
    )
    op.execute("UPDATE knowledge_documents SET indexing_status='NOT_INDEXED'")
    op.create_check_constraint(
        "indexing_status", "knowledge_documents", "indexing_status = 'NOT_INDEXED'"
    )
    op.drop_column("knowledge_documents", "publication_revision")
    op.drop_constraint(
        op.f("ck_knowledge_documents_evidence_revision"), "knowledge_documents", type_="check"
    )
    op.drop_column("knowledge_documents", "evidence_revision")
