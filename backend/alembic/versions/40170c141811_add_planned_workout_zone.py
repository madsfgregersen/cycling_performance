"""add planned workout zone

Revision ID: 40170c141811
Revises: f4612407cc02
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40170c141811'
down_revision: Union[str, Sequence[str], None] = 'f4612407cc02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("planned_workouts", sa.Column("zone", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("planned_workouts", "zone")
