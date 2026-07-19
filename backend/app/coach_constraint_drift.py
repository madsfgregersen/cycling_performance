import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, plan_constraints
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import PlannedWorkout, RideSummary

from .localtime import LOCAL_TZ
LOOKBACK_DAYS = 7

DRIFT_SCHEMA = {
    "type": "object",
    "properties": {
        "drifted": {
            "type": "boolean",
            "description": "True only if actual behavior clearly and specifically diverges from a stated constraint -- not a vague feeling.",
        },
        "headline": {"type": "string", "description": "One line naming the drift, or empty if drifted is false."},
        "why": {"type": "string", "description": "A short paragraph pointing at the specific constraint and the specific data that breaches it."},
        "note": {"type": "string", "description": "One actionable line, or an empty string."},
    },
    "required": ["drifted", "headline", "why", "note"],
    "additionalProperties": False,
}


def build_drift_context(db: Session):
    constraints = plan_constraints.list_constraints(db)
    if not constraints:
        return None

    today = datetime.now(LOCAL_TZ).date()
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    cutoff_start_local = datetime.combine(cutoff, datetime.min.time(), tzinfo=LOCAL_TZ)

    rides = (
        db.query(RideSummary)
        .filter(RideSummary.start_date >= cutoff_start_local)
        .order_by(RideSummary.start_date)
        .all()
    )
    planned = (
        db.query(PlannedWorkout)
        .filter(PlannedWorkout.date >= cutoff, PlannedWorkout.date <= today)
        .order_by(PlannedWorkout.date)
        .all()
    )

    return {
        "standing_constraints": [c["text"] for c in constraints],
        "last_7_days_actual_rides": [
            {
                "date": r.start_date.astimezone(LOCAL_TZ).date().isoformat(),
                "name": r.name,
                "tss": round(r.ride_tss, 1) if r.ride_tss else None,
            }
            for r in rides
        ],
        "last_7_days_planned": [
            {"date": w.date.isoformat(), "target_tss": w.target_tss, "zone": w.zone, "notes": w.notes}
            for w in planned
        ],
    }


def explain_drift(db: Session, context: dict) -> dict:
    prompt = (
        "Here are the athlete's standing constraints and the last 7 days of "
        "actual vs planned riding:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nHas reality clearly drifted from any stated constraint? Only set "
        "drifted=true if you can point to a specific constraint and specific "
        "data that breaches it. If nothing has clearly drifted, set "
        "drifted=false and leave headline/why/note minimal."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, DRIFT_SCHEMA, category="constraint_drift")
