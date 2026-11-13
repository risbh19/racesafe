"""Store signups pending email verification."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration", JSONB, nullable=False),
    )
    op.create_index("ix_pending_registrations_expires_at", "pending_registrations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pending_registrations_expires_at", table_name="pending_registrations")
    op.drop_table("pending_registrations")
