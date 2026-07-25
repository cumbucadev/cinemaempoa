"""Adds alert_actions (issue #258): the append-only posted/dismissed log
for the live-computed /admin/alerts Pendentes view. The old `alerts` table
and its generation pipeline are removed in a later migration once the
route and CLI stop depending on them.

Revision ID: 20260724_000000
Revises: 20260721_000000
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260724_000000"
down_revision: Union[str, None] = "20260721_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screening_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("remind_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["screening_id"], ["screenings.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_actions_screening_id", "alert_actions", ["screening_id"])
    op.create_index("ix_alert_actions_action", "alert_actions", ["action"])


def downgrade() -> None:
    op.drop_index("ix_alert_actions_action", table_name="alert_actions")
    op.drop_index("ix_alert_actions_screening_id", table_name="alert_actions")
    op.drop_table("alert_actions")
