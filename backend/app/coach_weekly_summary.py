import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, plan_blocks
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import DailyReadiness, PlannedWorkout, RideLap, RideSummary

from .localtime import LOCAL_TZ

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


def find_week_ending_yesterday(db: Session, today: date):
    yesterday = today - timedelta(days=1)
    for week in plan_blocks.list_blocks(db):
        end = datetime.strptime(week["end"], "%Y-%m-%d").date()
        if end == yesterday:
            return week
    return None


def _session_shapes(db: Session, rides: list) -> list:
    """One compact 'shape' per ride so the weekly summary can read each
    session's structure -- the lap sequence (zone / minutes / NP, the athlete's
    lap-button presses) plus time-in-zone -- not just the week's TSS total.
    laps is null for a ride ridden without laps (an unstructured/endurance
    ride)."""
    shapes = []
    for ride in sorted(rides, key=lambda r: r.start_date):
        laps = (
            db.query(RideLap)
            .filter(RideLap.ride_id == ride.id)
            .order_by(RideLap.lap_index)
            .all()
        )
        compact = None
        time_in_zone = {}
        if laps:
            compact = []
            for lap in laps:
                minutes = (
                    round((lap.end_offset_s - lap.start_offset_s + 1) / 60, 1)
                    if lap.start_offset_s is not None and lap.end_offset_s is not None
                    else None
                )
                compact.append(
                    {
                        "zone": lap.intensity_zone,
                        "min": minutes,
                        "np": round(lap.normalized_power) if lap.normalized_power else None,
                    }
                )
                if lap.intensity_zone and minutes:
                    time_in_zone[lap.intensity_zone] = round(
                        time_in_zone.get(lap.intensity_zone, 0) + minutes, 1
                    )
        shapes.append(
            {
                "date": ride.start_date.astimezone(LOCAL_TZ).date().isoformat(),
                "name": ride.name,
                "tss": round(ride.ride_tss, 1) if ride.ride_tss else None,
                "moving_min": round(ride.moving_time_s / 60) if ride.moving_time_s else None,
                "time_in_zone_min": time_in_zone or None,
                "laps": compact,
            }
        )
    return shapes


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
        "sessions": _session_shapes(db, rides),
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
        "readiness numbers given -- if a value is null, don't state it.\n\n"
        "The 'sessions' list gives each ride's structure via its laps (the "
        "athlete's lap-button presses -- zone / minutes / NP per lap). Judge "
        "the week by its SESSIONS, not just total TSS: recognize each key "
        "workout's interval type (over-unders alternate z4/z5 'overs' with z3 "
        "'unders'; threshold = sustained z4; VO2 = short z5 reps; sweet-spot = "
        "high z3 / low z4; endurance = z2) and whether the work was executed "
        "-- ignoring the long z1/z2 warm-up and cool-down laps. Then roll it up: "
        "e.g. 'two solid threshold sessions and a long endurance ride -- on "
        "plan for the block's z4 focus.' A ride with laps=null is an "
        "unstructured/endurance ride; don't invent structure for it."
    )
    return ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, WEEKLY_SUMMARY_SCHEMA, category="weekly_summary")
