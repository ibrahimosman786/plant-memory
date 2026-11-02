"""initial schema, row-level security, search triggers

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

from plant_memory.db.models import Base
from plant_memory.db.rls import rls_statements

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    # The initial schema is created from the declarative metadata; later changes are explicit
    # expand-then-contract migrations (see docs/runbook.md).
    Base.metadata.create_all(bind)

    # Lexical search vector maintained by trigger.
    bind.execute(sa.text("""
        CREATE OR REPLACE FUNCTION evidence_chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.text, '')) ||
                     to_tsvector('simple', coalesce(array_to_string(NEW.tags, ' '), ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS evidence_chunks_tsv ON evidence_chunks"))
    bind.execute(sa.text("""
        CREATE TRIGGER evidence_chunks_tsv BEFORE INSERT OR UPDATE ON evidence_chunks
        FOR EACH ROW EXECUTE FUNCTION evidence_chunks_tsv_update();
    """))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_evidence_chunks_embedding ON evidence_chunks USING hnsw (embedding vector_cosine_ops)"))
    bind.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_equipment_normalized_trgm ON equipment USING gin (normalized_tag gin_trgm_ops)"))

    for stmt in rls_statements():
        for piece in [s for s in stmt.split(";") if s.strip()]:
            bind.execute(sa.text(piece))

    # Runtime role grants (idempotent; role exists in local compose and in Terraform-managed RDS).
    bind.execute(sa.text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pm_app') THEN
            GRANT USAGE ON SCHEMA public TO pm_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pm_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pm_app;
          END IF;
        END $$;
    """))


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
