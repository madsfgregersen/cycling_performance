"""add checkin ride link

Revision ID: c9a1f2d8b3e4
Revises: a417e66cd5cf
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9a1f2d8b3e4'
down_revision: Union[str, Sequence[str], None] = 'a417e66cd5cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "telegram_checkins",
        sa.Column("ride_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_telegram_checkins_ride_id",
        "telegram_checkins",
        "rides_summary",
        ["ride_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_telegram_checkins_ride_id", "telegram_checkins", type_="foreignkey")
    op.drop_column("telegram_checkins", "ride_id")
