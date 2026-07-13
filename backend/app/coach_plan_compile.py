import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import ai_coach, plan_blocks, plan_constraints
from .coach_plan_adjust import (
    LOCAL_TZ,
    PROPOSAL_SCHEMA,
    _hard_boundary,
    _recent_rides,
)
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import DailyReadiness, PlannedWorkout

# How far ahead to show already-scheduled sessions, so the coach can update
# an existing day rather than double-book it.
UPCOMING_DAYS = 14


def build_compile_context(db: Session, today):
    """The intent the coach compiles from: the block(s) the target day could
    fall in, what's already on the calendar nearby, the standing constraints,
    and current load -- so a generated session fits the plan and the athlete.

    Reuses coach_plan_adjust's guardrail and recent-ride view so the hard
    boundary and load picture never diverge between the two flows."""
    current = plan_blocks.current_block(db, today)
    upcoming = (
        db.query(PlannedWorkout)
        .filter(PlannedWorkout.date >= today, PlannedWorkout.date <= today + timedelta(days=UPCOMING_DAYS))
        .order_by(PlannedWorkout.date)
        .all()
    )
    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()

    return {
        "today": today.isoformat(),
        "current_block": current,
        "all_blocks": plan_blocks.list_blocks(db),
        "upcoming_planned_workouts": [
            {"id": w.id, "date": w.date.isoformat(), "target_tss": w.target_tss, "zone": w.zone, "notes": w.notes}
            for w in upcoming
        ],
        "standing_constraints": [c["text"] for c in plan_constraints.list_constraints(db)],
        "readiness": (
            {
                "ctl": round(latest.ctl, 1) if latest.ctl is not None else None,
                "atl": round(latest.atl, 1) if latest.atl is not None else None,
                "tsb": round(latest.tsb, 1) if latest.tsb is not None else None,
                "verdict": latest.verdict,
            }
            if latest is not None
            else None
        ),
        "recent_rides": _recent_rides(db, today),
        "guardrail_hard_boundary": _hard_boundary(db).isoformat(),
    }


def propose_compilation(db: Session, message_text: str):
    """Story 12, single-workout scope: compile a block's intent into ONE
    concrete session for the day the athlete means. Returns
    {"summary": str, "changes": [...]} guardrail-filtered and capped to a
    single change, or None if the coach isn't configured.

    Writes nothing -- the returned changes ride the shared propose-confirm-
    write flow (coach_conversation._propose_and_log), applied only on
    confirmation by coach_plan_adjust.apply_changes."""
    today = datetime.now(LOCAL_TZ).date()
    context = build_compile_context(db, today)

    prompt = (
        f'The athlete asked you to compile a concrete session: "{message_text}"\n\n'
        "Here is the plan intent and current calendar:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nCompile the intent of the block that the requested day falls in into "
        "EXACTLY ONE concrete session for that single day (default to today if the "
        "day is unclear). Use action 'create' for a new day; use 'update' only if a "
        "workout already exists that day, and then only with its id from "
        "upcoming_planned_workouts. Set target_tss and zone from the block's focus, "
        "the standing constraints, and recent load. The date must be strictly before "
        "guardrail_hard_boundary (never on or after it -- non-negotiable). Return "
        "exactly one change. If a session genuinely shouldn't be added (e.g. the day "
        "is a rest day under the constraints, or past the guardrail), return an empty "
        "changes list and explain why in summary."
    )
    result = ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, PROPOSAL_SCHEMA)
    if not result:
        return None

    valid_ids = {w["id"] for w in context["upcoming_planned_workouts"]}
    hard_boundary = _hard_boundary(db)

    safe_changes = []
    for change in result.get("changes", []):
        try:
            change_date = datetime.strptime(change["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if change_date >= hard_boundary:
            continue
        if change.get("action") in ("update", "delete") and change.get("workout_id") not in valid_ids:
            continue
        safe_changes.append(change)
        break  # single-workout scope: one session only, never a batch

    return {"summary": result.get("summary", ""), "changes": safe_changes}
