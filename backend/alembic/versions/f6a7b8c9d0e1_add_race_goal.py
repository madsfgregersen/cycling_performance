"""add race goal

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    race_goal = op.create_table(
        "race_goal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("hills", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Seed with the exact facts that were previously hardcoded in
    # race_plan.py -- pure storage move, nothing changes until edited.
    op.bulk_insert(
        race_goal,
        [
            {
                "id": 1,
                "name": "Geo Park Gran Fondo",
                "date": "2026-08-30",
                "distance_km": 150,
                "elevation_m": 2000,
                "hills": 12,
            }
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("race_goal")
