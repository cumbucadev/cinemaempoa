"""Adiciona cinema Cine Cinco

Revision ID: 20260719_000000
Revises: 20260716_000000
Create Date: 2026-07-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260719_000000"
down_revision: Union[str, None] = "20260716_000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


cinemas_table = sa.table(
    "cinemas",
    sa.column("slug", sa.String),
    sa.column("name", sa.String),
    sa.column("url", sa.String),
)


def upgrade() -> None:
    op.bulk_insert(
        cinemas_table,
        [
            {
                "slug": "cine-cinco",
                "name": "Cine Cinco",
                "url": "https://www.pucrs.br/cultura/projetos/cine-cinco/",
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM cinemas WHERE slug = 'cine-cinco'")
