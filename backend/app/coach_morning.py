import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, plan_blocks, race_goal, recovery_signals
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import DailyReadiness, PlannedWorkout, RideSummary, TelegramCheckin

LOCAL_TZ = dt_timezone(timedelta(hours=9))

RECENT_RIDE_DAYS = 3
RAMP_WINDOW_DAYS = 7

VERDICT_EXPLANATION_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One line, e.g. 'Amber — load's the drag, not sleep.'"},
        "why": {"type": "string", "description": "A short paragraph explaining the read in the coach's voice."},
        "note": {"type": "string", "description": "One actionable line for today, or an empty string if none is useful."},
    },
    "required": ["headline", "why", "note"],
    "additionalProperties": False,
}


def _local_date(ts: datetime) -> date:
    return ts.astimezone(LOCAL_TZ).date()


def _load_ramp(db: Session) -> dict:
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=2 * RAMP_WINDOW_DAYS)
    rides = db.query(RideSummary).filter(RideSummary.start_date >= cutoff).all()

    today = date.today()
    this_window = 0.0
    prior_window = 0.0
    for ride in rides:
        days_ago = (today - _local_date(ride.start_date)).days
        tss = ride.ride_tss or 0.0
        if 0 <= days_ago < RAMP_WINDOW_DAYS:
            this_window += tss
        elif RAMP_WINDOW_DAYS <= days_ago < 2 * RAMP_WINDOW_DAYS:
            prior_window += tss

    ramp_pct = (
        round((this_window - prior_window) / prior_window * 100) if prior_window > 0 else None
    )
    return {
        "last_7_days_tss": round(this_window, 1),
        "prior_7_days_tss": round(prior_window, 1),
        "ramp_pct": ramp_pct,
    }


def _recent_rides(db: Session) -> list:
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=RECENT_RIDE_DAYS)
    rides = (
        db.query(RideSummary)
        .filter(RideSummary.start_date >= cutoff)
        .order_by(RideSummary.start_date)
        .all()
    )
    return [
        {
            "date": _local_date(r.start_date).isoformat(),
            "name": r.name,
            "distance_km": round(r.distance_m / 1000, 1) if r.distance_m else None,
            "tss": round(r.ride_tss, 1) if r.ride_tss else None,
        }
        for r in rides
    ]


def _yesterdays_checkin(db: Session, yesterday: date):
    row = (
        db.query(TelegramCheckin)
        .filter(TelegramCheckin.date == yesterday)
        .order_by(TelegramCheckin.created_at.desc())
        .first()
    )
    return row.raw_message if row else None


def _todays_planned_workout(db: Session, today: date):
    row = db.query(PlannedWorkout).filter(PlannedWorkout.date == today).first()
    if row is None:
        return None
    return {"target_tss": row.target_tss, "zone": row.zone, "notes": row.notes}


def build_morning_context(db: Session):
    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()
    if latest is None:
        return None

    today = date.today()
    yesterday = today - timedelta(days=1)
    goal = race_goal.get_goal(db)
    event_date = datetime.strptime(goal["date"], "%Y-%m-%d").date()

    return {
        "verdict": {
            "color": latest.verdict,
            "date": latest.date.isoformat(),
            "ctl": round(latest.ctl, 1) if latest.ctl is not None else None,
            "atl": round(latest.atl, 1) if latest.atl is not None else None,
            "tsb": round(latest.tsb, 1) if latest.tsb is not None else None,
        },
        "load_ramp": _load_ramp(db),
        "recovery_deviations": recovery_signals.get_recovery_deviations(db),
        "recent_rides": _recent_rides(db),
        "yesterdays_checkin": _yesterdays_checkin(db, yesterday),
        "goal": {**goal, "days_remaining": (event_date - today).days},
        "current_block": plan_blocks.current_block(db, today),
        "todays_planned_workout": _todays_planned_workout(db, today),
    }


def explain_verdict(db: Session) -> dict:
    context = build_morning_context(db)
    if context is None:
        return {}

    prompt = (
        "Here is today's data:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nExplain today's readiness verdict per your instructions."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, VERDICT_EXPLANATION_SCHEMA)
