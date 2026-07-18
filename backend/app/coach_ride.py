import json
from datetime import timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, ride_metrics
from .activity_log import log_event
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import IntegrationLog, PlannedWorkout, TelegramCheckin

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
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, RIDE_DEBRIEF_SCHEMA, category="ride_debrief")


def _brief_marker(ride) -> str:
    # Trailing " |" delimiter so a LIKE lookup can't collide (1001 vs 10011).
    return f"strava_activity_id={ride.strava_activity_id}"


def get_cached_ride_brief(db: Session, ride):
    """The cached post-ride debrief (headline/why/note) for this ride, or
    None if none has been generated. No LLM call."""
    row = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.source == "coach",
            IntegrationLog.event == "ride_brief",
            IntegrationLog.summary.like(_brief_marker(ride) + " |%"),
        )
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    if row is None:
        return None
    try:
        return json.loads(row.summary.split(" | ", 1)[1])
    except (ValueError, IndexError):
        return None


def cache_ride_brief(db: Session, ride):
    """Compute the debrief once and cache it as an IntegrationLog row (like
    the morning brief -- no new table). Idempotent per ride, so it's safe to
    call from the ride-landed flow regardless of Telegram settings, and again
    from the debrief sender without a second LLM call. Returns the dict, or
    None if the coach isn't configured."""
    existing = get_cached_ride_brief(db, ride)
    if existing is not None:
        return existing
    explanation = explain_ride(db, ride)
    if not explanation:
        return None
    log_event(
        db,
        "coach",
        "ride_brief",
        _brief_marker(ride)
        + " | "
        + json.dumps(
            {
                "headline": explanation.get("headline", ""),
                "why": explanation.get("why", ""),
                "note": explanation.get("note", ""),
            }
        ),
    )
    return explanation


def ride_feel_reply(db: Session, ride):
    """The athlete's RPE/feel reply tied to this ride (story 4), or None."""
    row = (
        db.query(TelegramCheckin)
        .filter(TelegramCheckin.ride_id == ride.id)
        .order_by(TelegramCheckin.created_at.desc())
        .first()
    )
    return row.raw_message if row and row.raw_message else None


def _evaluation_from_sent_debrief(db: Session, ride):
    """Fallback for rides whose debrief was sent before structured ride_brief
    caching existed: recover the coach's evaluation from the Telegram debrief
    that was logged. The sent message is
    '{headline}\\n\\n{why}\\n\\n[{note}]\\n\\n[{feel-ask}]', so the evaluation
    -- the coach's interpretation of the ride -- is the 2nd paragraph."""
    row = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.source == "telegram",
            IntegrationLog.event == "ride_debrief_sent",
            IntegrationLog.summary.like(f"ride_id={ride.id} |%"),
        )
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    if row is None:
        return None
    text = row.summary.split(" | ", 1)[1] if " | " in row.summary else row.summary
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paras) < 2:
        return None
    return {"headline": paras[0], "why": paras[1], "note": ""}


def ride_evaluation(db: Session, ride):
    """The coach's evaluation for a ride's calendar tile: the structured cache
    if present, otherwise recovered from the debrief that was already sent.
    None if neither exists."""
    return get_cached_ride_brief(db, ride) or _evaluation_from_sent_debrief(db, ride)
