"""initial schema

Revision ID: 553d6bdab54c
Revises: 
Create Date: 2026-07-11 16:18:15.011427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '553d6bdab54c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rides_summary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("moving_time_s", sa.Integer(), nullable=True),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("average_watts", sa.Float(), nullable=True),
        sa.Column("weighted_avg_watts", sa.Float(), nullable=True),
        sa.Column("average_heartrate", sa.Float(), nullable=True),
        sa.Column("max_heartrate", sa.Float(), nullable=True),
        sa.Column("ride_tss", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("strava_activity_id"),
    )

    op.create_table(
        "ride_streams",
        sa.Column(
            "ride_id",
            sa.Integer(),
            sa.ForeignKey("rides_summary.id"),
            primary_key=True,
        ),
        sa.Column("second_offset", sa.Integer(), primary_key=True),
        sa.Column("watts", sa.Float(), nullable=True),
        sa.Column("heartrate", sa.Float(), nullable=True),
        sa.Column("cadence", sa.Float(), nullable=True),
        sa.Column("altitude", sa.Float(), nullable=True),
        sa.Column("velocity_smooth", sa.Float(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
    )

    op.create_table(
        "health_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "telegram_checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("raw_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "daily_readiness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ctl", sa.Float(), nullable=True),
        sa.Column("atl", sa.Float(), nullable=True),
        sa.Column("tsb", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("date"),
    )

    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("target_tss", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("planned_workouts")
    op.drop_table("daily_readiness")
    op.drop_table("telegram_checkins")
    op.drop_table("health_samples")
    op.drop_table("ride_streams")
    op.drop_table("rides_summary")
