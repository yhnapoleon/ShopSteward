"""Agent-owned knowledge schema and atomic follow-up publication fingerprint."""

import sqlalchemy as sa
from alembic import op

revision = "0009_agent_scopes"
down_revision = "0008_agent_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS agent_data")
    op.execute("ALTER TABLE public.agent_knowledge_scopes SET SCHEMA agent_data")
    op.execute("ALTER TABLE public.agent_knowledge_revisions SET SCHEMA agent_data")
    op.add_column("agent_runs", sa.Column("trigger_fingerprint", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("agent_runs", "trigger_fingerprint")
    op.execute("ALTER TABLE agent_data.agent_knowledge_revisions SET SCHEMA public")
    op.execute("ALTER TABLE agent_data.agent_knowledge_scopes SET SCHEMA public")
