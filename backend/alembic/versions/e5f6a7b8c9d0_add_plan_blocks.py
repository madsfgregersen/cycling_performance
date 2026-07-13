"""add plan blocks

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "plan_adjustment_proposals",
        sa.Column("kind", sa.String(), nullable=False, server_default="workout"),
    )

    plan_blocks = op.create_table(
        "plan_blocks",
        sa.Column("week", sa.Integer(), primary_key=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("focus", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Seed with the exact content that was previously hardcoded in
    # race_plan.py, so this migration is a pure storage move -- nothing
    # about the live plan changes until someone actually edits a block.
    op.bulk_insert(
        plan_blocks,
        [
            {
                "week": 1,
                "start_date": "2026-07-13",
                "end_date": "2026-07-19",
                "phase": "build",
                "label": "Build",
                "focus": "Wake up the top end",
                "detail": (
                    "Reintroduce structured intensity. Threshold: 3x10 min @ "
                    "95-100%. VO2 opener: 5x3 min @ ~115%. Long endurance: 3-4 hrs "
                    "Z2 over rolling terrain. ~8-10 hrs."
                ),
            },
            {
                "week": 2,
                "start_date": "2026-07-20",
                "end_date": "2026-07-26",
                "phase": "build",
                "label": "Build",
                "focus": "Threshold volume",
                "detail": (
                    "Push threshold duration; introduce race-specific over-unders. "
                    "Threshold: 2x20 min @ 95-100%. Over-unders: 3x[2 min @ 105% / "
                    "3 min @ 88-90%]. Long ride: 4 hrs hitting 4-6 short climbs at "
                    "tempo/threshold. ~9-11 hrs."
                ),
            },
            {
                "week": 3,
                "start_date": "2026-07-27",
                "end_date": "2026-08-02",
                "phase": "build",
                "label": "Build Peak",
                "focus": "Biggest load",
                "detail": (
                    "Your hardest week; expect real fatigue by the end. "
                    "Threshold: 3x12 min. VO2: 5x4 min @ 115%. Longest ride: "
                    "4.5-5 hrs simulating rolling terrain. Second easy endurance "
                    "ride. ~10-12 hrs."
                ),
            },
            {
                "week": 4,
                "start_date": "2026-08-03",
                "end_date": "2026-08-09",
                "phase": "recovery",
                "label": "Recovery",
                "focus": "Absorption",
                "detail": (
                    "Cut volume 40-50%, mostly easy. This is where the last three "
                    "weeks turn into fitness. One light opener: 3x5 min tempo. "
                    "Optional FTP re-test at week's end. ~5-6 hrs."
                ),
            },
            {
                "week": 5,
                "start_date": "2026-08-10",
                "end_date": "2026-08-16",
                "phase": "specificity",
                "label": "Specificity",
                "focus": "Race simulation begins",
                "detail": (
                    "Everything now points at the event. Longer over-unders: "
                    "4x[3 min over / 3 min under]. Hill repeats at event gradient: "
                    "6-8x4-6 min @ threshold, recover on descent. 4-4.5 hr ride: "
                    "go hard on every hill, practice recovering between them. "
                    "~9-11 hrs."
                ),
            },
            {
                "week": 6,
                "start_date": "2026-08-17",
                "end_date": "2026-08-23",
                "phase": "specificity",
                "label": "Specificity Peak",
                "focus": "Last big ride",
                "detail": (
                    "Highest-quality week, front-loaded. Big race-simulation ride "
                    "early/mid-week: ~4-5 hrs, hills at goal effort, fueling and "
                    "pacing exactly as race day. One shorter sharp session. Start "
                    "easing by the weekend. ~8-10 hrs, tapering into Sunday."
                ),
            },
            {
                "week": 7,
                "start_date": "2026-08-24",
                "end_date": "2026-08-30",
                "phase": "taper",
                "label": "Taper + Race",
                "focus": "Race day",
                "detail": (
                    "Volume down ~50-60% from peak; keep riding most days but "
                    "short. Openers 2-3 days out: short spin with a few 1-2 min "
                    "efforts at race intensity. Easy spin or full rest the day "
                    "before. Race: Sunday, Aug 30. Priority is freshness, sleep, "
                    "and logistics -- not fitness."
                ),
            },
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("plan_blocks")
    op.drop_column("plan_adjustment_proposals", "kind")
