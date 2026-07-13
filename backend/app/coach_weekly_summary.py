import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, race_plan
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import DailyReadiness, PlannedWorkout, RideSummary

LOCAL_TZ = dt_timezone(timedelta(hours=9))

WEEKLY_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One line summing up how the week went."},
        "why": {"type": "string", "description": "A short paragraph comparing what actually happened to what the block called for."},
        "note": {"type": "string", "description": "One actionable line for the week ahead, or an empty string if none is useful."},
    },
    "required": ["headline", "why", "note"],
    "additionalProperties": False,
}


def find_week_ending_yesterday(today: date):
    yesterday = today - timedelta(days=1)
    for week in race_plan.WEEKS:
        end = datetime.strptime(week["end"], "%Y-%m-%d").date()
        if end == yesterday:
            return week
    return None


def build_weekly_context(db: Session, week: dict) -> dict:
    start = datetime.strptime(week["start"], "%Y-%m-%d").date()
    end = datetime.strptime(week["end"], "%Y-%m-%d").date()

    # Bound on local calendar days, not the UTC-stored timestamp column
    # directly -- a ride near either edge of the week would otherwise be
    # miscounted by the JST offset.
    week_start_local = datetime.combine(start, datetime.min.time(), tzinfo=LOCAL_TZ)
    week_end_local = datetime.combine(end, datetime.min.time(), tzinfo=LOCAL_TZ) + timedelta(days=1)
    rides = (
        db.query(RideSummary)
        .filter(RideSummary.start_date >= week_start_local, RideSummary.start_date < week_end_local)
        .all()
    )
    total_tss = sum(r.ride_tss or 0.0 for r in rides)
    total_hours = sum(r.moving_time_s or 0 for r in rides) / 3600

    planned = db.query(PlannedWorkout).filter(PlannedWorkout.date >= start, PlannedWorkout.date <= end).all()
    planned_tss = sum(w.target_tss or 0.0 for w in planned)

    readiness_start = db.query(DailyReadiness).filter(DailyReadiness.date == start).first()
    readiness_end = db.query(DailyReadiness).filter(DailyReadiness.date == end).first()

    return {
        "week": week["week"],
        "label": week["label"],
        "focus": week["focus"],
        "plan_detail": week["detail"],
        "dates": {"start": week["start"], "end": week["end"]},
        "actual": {
            "ride_count": len(rides),
            "total_tss": round(total_tss, 1),
            "total_hours": round(total_hours, 1),
        },
        "planned": {
            "workout_count": len(planned),
            "total_target_tss": round(planned_tss, 1),
        },
        "readiness": {
            "ctl_start": round(readiness_start.ctl, 1) if readiness_start and readiness_start.ctl is not None else None,
            "ctl_end": round(readiness_end.ctl, 1) if readiness_end and readiness_end.ctl is not None else None,
            "atl_end": round(readiness_end.atl, 1) if readiness_end and readiness_end.atl is not None else None,
            "tsb_end": round(readiness_end.tsb, 1) if readiness_end and readiness_end.tsb is not None else None,
        },
    }


def explain_week(db: Session, context: dict) -> dict:
    prompt = (
        "Here is how this training block week actually went, versus what it called for:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nWrite a short weekly summary. Compare actual TSS/hours/rides to "
        "what was planned and to the block's stated focus. Only use the "
        "readiness numbers given -- if a value is null, don't state it."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, WEEKLY_SUMMARY_SCHEMA)
