"""Classify team drafts and store invite versions and shared rate limits."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column(
        "is_draft", sa.Boolean(), sa.Computed("member_count < min_size", persisted=True),
        nullable=False,
    ))
    op.add_column("teams", sa.Column(
        "invite_version", sa.Integer(), server_default=sa.text("0"), nullable=False,
    ))
    op.create_index(
        "ix_audit_archived_teams", "audit_log", ["actor_id", "id"],
        postgresql_where=sa.text("action = 'team.deleted'"),
    )
    op.create_table(
        "rate_limits",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limits_expires_at", "rate_limits", ["expires_at"])


def downgrade() -> None:
    op.drop_table("rate_limits")
    op.drop_index("ix_audit_archived_teams", table_name="audit_log")
    op.drop_column("teams", "invite_version")
    op.drop_column("teams", "is_draft")
