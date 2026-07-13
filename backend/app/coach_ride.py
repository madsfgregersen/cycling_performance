import json
from datetime import timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, ride_metrics
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import PlannedWorkout

LOCAL_TZ = dt_timezone(timedelta(hours=9))

RIDE_DEBRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One line summing up the ride."},
        "why": {"type": "string", "description": "A short paragraph interpreting the ride against what it was for."},
        "note": {"type": "string", "description": "One actionable line, or an empty string if none is useful."},
    },
    "required": ["headline", "why", "note"],
    "additionalProperties": False,
}


def _planned_workout_for(db: Session, ride_local_date):
    row = db.query(PlannedWorkout).filter(PlannedWorkout.date == ride_local_date).first()
    if row is None:
        return None
    return {"target_tss": row.target_tss, "zone": row.zone, "notes": row.notes}


def build_ride_context(db: Session, ride) -> dict:
    ride_local_date = ride.start_date.astimezone(LOCAL_TZ).date()
    metrics = ride_metrics.compute_ride_metrics(db, ride)

    return {
        "ride": {
            "date": ride_local_date.isoformat(),
            "name": ride.name,
            "distance_km": round(ride.distance_m / 1000, 1) if ride.distance_m else None,
            "moving_time_minutes": round(ride.moving_time_s / 60) if ride.moving_time_s else None,
            "elevation_gain_m": ride.elevation_gain_m,
            "average_watts": ride.average_watts,
            "weighted_avg_watts": ride.weighted_avg_watts,
            "average_heartrate": ride.average_heartrate,
            "max_heartrate": ride.max_heartrate,
            "tss": round(ride.ride_tss, 1) if ride.ride_tss else None,
        },
        "efficiency_factor": metrics["efficiency_factor"],
        "decoupling_pct": metrics["decoupling_pct"],
        "planned_workout_that_day": _planned_workout_for(db, ride_local_date),
    }


def explain_ride(db: Session, ride) -> dict:
    context = build_ride_context(db, ride)

    prompt = (
        "Here is a ride that just landed:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nWrite a short post-ride debrief. Interpret efficiency factor and "
        "decoupling if given (decoupling_pct is null if there wasn't enough "
        "data to call it -- don't mention it in that case). If a planned "
        "workout existed that day, judge the ride against what it was for; "
        "if planned_workout_that_day is null, it was an unplanned/extra ride "
        "-- say so rather than inventing a purpose for it."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, RIDE_DEBRIEF_SCHEMA)
