import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import PlannedWorkout, RideSummary

LOCAL_TZ = dt_timezone(timedelta(hours=9))

MISSED_WORKOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One line naming what was missed."},
        "why": {"type": "string", "description": "A short paragraph on what this means -- without silently assuming it'll be made up later."},
        "note": {"type": "string", "description": "One actionable line, or an empty string if none is useful."},
    },
    "required": ["headline", "why", "note"],
    "additionalProperties": False,
}


def _ride_landed_on(db: Session, local_day: date) -> bool:
    # Rides are timestamped in UTC; bound the query to the local calendar
    # day rather than casting the column, so a ride landing late UTC-evening
    # still counts for its local date.
    day_start_local = datetime.combine(local_day, datetime.min.time(), tzinfo=LOCAL_TZ)
    day_end_local = day_start_local + timedelta(days=1)
    return (
        db.query(RideSummary)
        .filter(
            RideSummary.start_date >= day_start_local,
            RideSummary.start_date < day_end_local,
        )
        .first()
        is not None
    )


def build_missed_workout_context(db: Session, checked_date: date):
    planned = db.query(PlannedWorkout).filter(PlannedWorkout.date == checked_date).all()
    if not planned:
        return None

    if _ride_landed_on(db, checked_date):
        return None

    return {
        "date": checked_date.isoformat(),
        "planned_workouts": [
            {"target_tss": w.target_tss, "zone": w.zone, "notes": w.notes} for w in planned
        ],
    }


def explain_missed_workout(db: Session, context: dict) -> dict:
    prompt = (
        "Here is a workout that was planned but no ride landed for that date:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nNudge the athlete about it. Name what was missed. Don't silently "
        "assume it will be made up on a later day -- flag it plainly and let "
        "the athlete decide what to do about it."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, MISSED_WORKOUT_SCHEMA)
