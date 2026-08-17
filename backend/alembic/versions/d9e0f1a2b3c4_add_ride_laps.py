"""add ride laps

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ride_laps",
        sa.Column("ride_id", sa.Integer(), sa.ForeignKey("rides_summary.id"), primary_key=True),
        sa.Column("lap_index", sa.Integer(), primary_key=True),
        sa.Column("start_offset_s", sa.Integer(), nullable=True),
        sa.Column("end_offset_s", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("moving_time_s", sa.Integer(), nullable=True),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("avg_power", sa.Float(), nullable=True),
        sa.Column("normalized_power", sa.Float(), nullable=True),
        sa.Column("max_power", sa.Float(), nullable=True),
        sa.Column("avg_hr", sa.Float(), nullable=True),
        sa.Column("max_hr", sa.Float(), nullable=True),
        sa.Column("avg_cadence", sa.Float(), nullable=True),
        sa.Column("avg_speed", sa.Float(), nullable=True),
        sa.Column("intensity_factor", sa.Float(), nullable=True),
        sa.Column("lap_tss", sa.Float(), nullable=True),
        sa.Column("intensity_zone", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ride_laps")
