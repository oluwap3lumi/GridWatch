"""Keep inference provenance and explicit defaults with each derived score.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy scores have unknown inference provenance until their next rescore.
    op.add_column(
        "risk_scores",
        sa.Column(
            "inference_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("risk_scores", "inference_metadata")
