"""Adds cinema profile fields (address, opening hours, Instagram, map
embed, photo) so /cinemas/<slug> can show venue info - see
docs/superpowers/specs/2026-07-27-cinema-pages-design.md.

Revision ID: 20260727_000001
Revises: 20260727_000000
Create Date: 2026-07-27 00:00:01.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260727_000001"
down_revision: Union[str, None] = "20260727_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cinemas", sa.Column("address", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("opening_hours", sa.Text(), nullable=True))
    op.add_column("cinemas", sa.Column("instagram_url", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("map_embed_url", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("photo", sa.String(), nullable=True))
    op.add_column("cinemas", sa.Column("photo_width", sa.Integer(), nullable=True))
    op.add_column("cinemas", sa.Column("photo_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cinemas", "photo_height")
    op.drop_column("cinemas", "photo_width")
    op.drop_column("cinemas", "photo")
    op.drop_column("cinemas", "map_embed_url")
    op.drop_column("cinemas", "instagram_url")
    op.drop_column("cinemas", "opening_hours")
    op.drop_column("cinemas", "address")
