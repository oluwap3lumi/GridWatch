"""Record the prediction cutoff separately from the actual scoring timestamp.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy scores have no recoverable cutoff; preserve them without inventing provenance.
    op.add_column("risk_scores", sa.Column("prediction_cutoff", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("risk_scores", "prediction_cutoff")
