"""Immutable learning foundation DDL; generated once, independent of runtime models."""

from alembic import op

revision = "0016_learning_foundation"
down_revision = "0015_operations_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE agent_data.learning_policies (
	id VARCHAR(64) NOT NULL, 
	principal_id VARCHAR(128) NOT NULL, 
	store_id VARCHAR(128) NOT NULL, 
	source_domain VARCHAR(16) NOT NULL, 
	version INTEGER NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	enabled_at TIMESTAMP WITH TIME ZONE, 
	blocked_concepts JSONB NOT NULL, 
	consumed JSONB NOT NULL, 
	CONSTRAINT pk_learning_policies PRIMARY KEY (id), 
	CONSTRAINT uq_learning_policies_principal_id UNIQUE (principal_id, store_id, source_domain), 
	FOREIGN KEY(store_id) REFERENCES stores (id)
)

""")
    op.execute("""
CREATE TABLE agent_data.learning_assets (
	id VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(64) NOT NULL, 
	kind VARCHAR(24) NOT NULL, 
	task_family VARCHAR(80) NOT NULL, 
	concept_key VARCHAR(64) NOT NULL, 
	version INTEGER NOT NULL, 
	latest_revision INTEGER NOT NULL, 
	active_revision INTEGER, 
	CONSTRAINT pk_learning_assets PRIMARY KEY (id), 
	CONSTRAINT uq_learning_assets_scope_id UNIQUE (scope_id, concept_key), 
	FOREIGN KEY(scope_id) REFERENCES agent_data.learning_policies (id)
)

""")
    op.execute("CREATE INDEX ix_learning_assets_scope_id ON agent_data.learning_assets (scope_id)")
    op.execute("""
CREATE TABLE agent_data.learning_batches (
	id VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(64) NOT NULL, 
	policy_version INTEGER NOT NULL, 
	trigger JSONB NOT NULL, 
	evidence_digest VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	usage JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_learning_batches PRIMARY KEY (id), 
	FOREIGN KEY(scope_id) REFERENCES agent_data.learning_policies (id)
)

""")
    op.execute(
        "CREATE INDEX ix_learning_batches_scope_id ON agent_data.learning_batches (scope_id)"
    )
    op.execute("""
CREATE TABLE agent_data.learning_outbox (
	id VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(64) NOT NULL, 
	policy_version INTEGER NOT NULL, 
	digest VARCHAR(64) NOT NULL, 
	document JSONB NOT NULL, 
	processed BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_learning_outbox PRIMARY KEY (id), 
	FOREIGN KEY(scope_id) REFERENCES agent_data.learning_policies (id)
)

""")
    op.execute("CREATE INDEX ix_learning_outbox_scope_id ON agent_data.learning_outbox (scope_id)")
    op.execute("""
CREATE TABLE agent_data.operation_episodes (
	id VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(64) NOT NULL, 
	intent_key VARCHAR(256) NOT NULL, 
	task_family VARCHAR(80) NOT NULL, 
	eligible BOOLEAN NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	evidence_ids JSONB NOT NULL, 
	outcome_revision INTEGER NOT NULL, 
	CONSTRAINT pk_operation_episodes PRIMARY KEY (id), 
	CONSTRAINT uq_operation_episodes_scope_id UNIQUE (scope_id, intent_key), 
	FOREIGN KEY(scope_id) REFERENCES agent_data.learning_policies (id)
)

""")
    op.execute(
        "CREATE INDEX ix_operation_episodes_scope_id ON agent_data.operation_episodes (scope_id)"
    )
    op.execute("""
CREATE TABLE agent_data.episode_events (
	event_id VARCHAR(64) NOT NULL, 
	episode_id VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_episode_events PRIMARY KEY (event_id), 
	FOREIGN KEY(event_id) REFERENCES agent_data.learning_outbox (id), 
	FOREIGN KEY(episode_id) REFERENCES agent_data.operation_episodes (id)
)

""")
    op.execute(
        "CREATE INDEX ix_episode_events_episode_id ON agent_data.episode_events (episode_id)"
    )
    op.execute("""
CREATE TABLE agent_data.episode_outcomes (
	episode_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	document JSONB NOT NULL, 
	available_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	CONSTRAINT pk_episode_outcomes PRIMARY KEY (episode_id, revision), 
	FOREIGN KEY(episode_id) REFERENCES agent_data.operation_episodes (id)
)

""")
    op.execute("""
CREATE TABLE agent_data.learning_applications (
	id VARCHAR(64) NOT NULL, 
	scope_id VARCHAR(64) NOT NULL, 
	asset_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	run_id VARCHAR(128) NOT NULL, 
	stage VARCHAR(24) NOT NULL, 
	outcome JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_learning_applications PRIMARY KEY (id), 
	FOREIGN KEY(scope_id) REFERENCES agent_data.learning_policies (id), 
	FOREIGN KEY(asset_id) REFERENCES agent_data.learning_assets (id)
)

""")
    op.execute(
        "CREATE INDEX ix_learning_applications_scope_id "
        "ON agent_data.learning_applications (scope_id)"
    )
    op.execute("""
CREATE TABLE agent_data.learning_asset_revisions (
	asset_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	spec JSONB NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	evidence_digest VARCHAR(64) NOT NULL, 
	evidence_ids JSONB NOT NULL, 
	evaluation_id VARCHAR(64), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_learning_asset_revisions PRIMARY KEY (asset_id, revision), 
	FOREIGN KEY(asset_id) REFERENCES agent_data.learning_assets (id)
)

""")
    op.execute("""
CREATE TABLE agent_data.learning_evaluations (
	id VARCHAR(64) NOT NULL, 
	asset_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	report JSONB NOT NULL, 
	decision JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_learning_evaluations PRIMARY KEY (id), 
	FOREIGN KEY(asset_id) REFERENCES agent_data.learning_assets (id)
)

""")
    op.execute(
        "CREATE INDEX ix_learning_evaluations_asset_id "
        "ON agent_data.learning_evaluations (asset_id)"
    )
    op.execute("""
CREATE TABLE agent_data.learning_evidence_links (
	event_id VARCHAR(64) NOT NULL, 
	asset_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	relation VARCHAR(24) NOT NULL, 
	CONSTRAINT pk_learning_evidence_links PRIMARY KEY (event_id, asset_id, revision), 
	FOREIGN KEY(event_id) REFERENCES agent_data.learning_outbox (id), 
	FOREIGN KEY(asset_id) REFERENCES agent_data.learning_assets (id)
)

""")
    op.execute(
        "ALTER TABLE agent_data.learning_policies ADD CONSTRAINT learning_policy_valid "
        "CHECK (mode IN ('off','suggest','assist') "
        "AND source_domain IN ('simulation','observed') AND version >= 0)"
    )
    op.execute(
        "ALTER TABLE agent_data.learning_assets ADD CONSTRAINT learning_asset_valid "
        "CHECK (kind IN ('SKILL','EXPERIENCE','WORKFLOW','UI') "
        "AND version >= 1 AND latest_revision >= 1)"
    )
    op.execute(
        "ALTER TABLE agent_data.learning_asset_revisions ADD CONSTRAINT learning_revision_valid "
        "CHECK (revision >= 1 AND status IN ('DRAFT','VALIDATING','SHADOW','ACTIVE','SUSPENDED',"
        "'SUPERSEDED','ARCHIVED','REVOKED','REJECTED'))"
    )
    op.execute("""CREATE FUNCTION agent_data.learning_revision_immutable()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.spec IS DISTINCT FROM OLD.spec OR NEW.content_hash <> OLD.content_hash
         OR NEW.evidence_ids IS DISTINCT FROM OLD.evidence_ids
         OR NEW.evidence_digest <> OLD.evidence_digest THEN
        RAISE EXCEPTION 'learning revision content is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER learning_revision_immutable "
        "BEFORE UPDATE ON agent_data.learning_asset_revisions "
        "FOR EACH ROW EXECUTE FUNCTION agent_data.learning_revision_immutable()"
    )


def downgrade():
    op.execute("DROP TRIGGER learning_revision_immutable ON agent_data.learning_asset_revisions")
    op.execute("DROP FUNCTION agent_data.learning_revision_immutable()")
    op.drop_table("learning_evidence_links", schema="agent_data")
    op.drop_table("learning_evaluations", schema="agent_data")
    op.drop_table("learning_asset_revisions", schema="agent_data")
    op.drop_table("learning_applications", schema="agent_data")
    op.drop_table("episode_outcomes", schema="agent_data")
    op.drop_table("episode_events", schema="agent_data")
    op.drop_table("operation_episodes", schema="agent_data")
    op.drop_table("learning_outbox", schema="agent_data")
    op.drop_table("learning_batches", schema="agent_data")
    op.drop_table("learning_assets", schema="agent_data")
    op.drop_table("learning_policies", schema="agent_data")
