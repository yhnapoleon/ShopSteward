"""K1 immutable originals and independently versioned document metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_knowledge"
down_revision = "0009_agent_scopes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(128), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("owner_principal_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("sku_ids", postgresql.JSONB(), nullable=False),
        sa.Column("supplier_ids", postgresql.JSONB(), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("metadata_version", sa.BigInteger(), nullable=False),
        sa.Column("latest_version_id", sa.String(128)),
        sa.Column("ingestion_status", sa.String(16), nullable=False),
        sa.Column("indexing_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("visibility IN ('store','private')", name="visibility"),
        sa.CheckConstraint("status IN ('active','archived')", name="status"),
        sa.CheckConstraint("metadata_version >= 1", name="metadata_version"),
        sa.CheckConstraint("ingestion_status = 'UPLOADED'", name="ingestion_status"),
        sa.CheckConstraint("indexing_status = 'NOT_INDEXED'", name="indexing_status"),
    )
    op.create_index(
        "ix_knowledge_documents_page",
        "knowledge_documents",
        ["store_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_knowledge_documents_skus", "knowledge_documents", ["sku_ids"], postgresql_using="gin"
    )
    op.create_index(
        "ix_knowledge_documents_suppliers",
        "knowledge_documents",
        ["supplier_ids"],
        postgresql_using="gin",
    )
    op.create_table(
        "knowledge_versions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "document_id", sa.String(128), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("version_no", sa.BigInteger(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("raw_key", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_id", "version_no", name="uq_knowledge_version_number"),
        sa.UniqueConstraint("document_id", "id", name="uq_knowledge_version_document_id"),
        sa.CheckConstraint("version_no >= 1", name="version_no"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 20971520", name="size_bytes"),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        sa.CheckConstraint("raw_key ~ '^[0-9a-f]{32}[.]raw$'", name="raw_key"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from", name="validity"
        ),
    )
    op.create_foreign_key(
        "fk_knowledge_latest_version",
        "knowledge_documents",
        "knowledge_versions",
        ["id", "latest_version_id"],
        ["document_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.execute("""
        CREATE FUNCTION knowledge_version_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Knowledge original versions are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER knowledge_version_immutable BEFORE UPDATE OR DELETE ON knowledge_versions
        FOR EACH ROW EXECUTE FUNCTION knowledge_version_immutable()
    """)


def downgrade():
    op.drop_constraint("fk_knowledge_latest_version", "knowledge_documents", type_="foreignkey")
    op.drop_table("knowledge_versions")
    op.execute("DROP FUNCTION knowledge_version_immutable()")
    op.drop_table("knowledge_documents")
