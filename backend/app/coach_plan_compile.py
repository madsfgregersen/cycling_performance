import json
from datetime import datetime

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


def _week_of(blocks: list, d):
    """The plan-block week number a date falls in, or None if it's outside
    every block (e.g. before the plan starts)."""
    for b in blocks:
        start = datetime.strptime(b["start"], "%Y-%m-%d").date()
        end = datetime.strptime(b["end"], "%Y-%m-%d").date()
        if start <= d <= end:
            return b["week"]
    return None


def _restrict_to_one_week(blocks: list, changes: list) -> list:
    """The code-enforced 'week by week' guarantee (story 12b): whatever the
    model returns, keep only the changes that fall in a single plan-block
    week -- the earliest week represented -- and drop anything outside a
    block week entirely. The coach can never write two weeks in one approval,
    even if it tries. A single-day compile (12a) is unaffected: one date sits
    in one week."""
    by_week = {}
    for change in changes:
        try:
            d = datetime.strptime(change["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        week = _week_of(blocks, d)
        if week is None:
            continue
        by_week.setdefault(week, []).append(change)
    if not by_week:
        return []
    earliest = min(by_week)
    return by_week[earliest]


def build_compile_context(db: Session, today):
    """The intent the coach compiles from: the block plan (so it can target a
    named week, a block's first empty week, or 'the next week'), everything
    already on the calendar (so it fills gaps rather than double-booking), the
    standing constraints, and current load.

    Reuses coach_plan_adjust's guardrail and recent-ride view so the hard
    boundary and load picture never diverge between the two flows."""
    blocks = plan_blocks.list_blocks(db)
    all_planned = db.query(PlannedWorkout).order_by(PlannedWorkout.date).all()
    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()

    planned_by_week = {}
    for w in all_planned:
        week = _week_of(blocks, w.date)
        if week is not None:
            planned_by_week[week] = planned_by_week.get(week, 0) + 1

    return {
        "today": today.isoformat(),
        "current_block": plan_blocks.current_block(db, today),
        # Per-week focus plus how many sessions are already scheduled, so the
        # coach can pick the first un-filled week of a block on its own.
        "blocks": [{**b, "planned_workout_count": planned_by_week.get(b["week"], 0)} for b in blocks],
        "planned_workouts": [
            {"id": w.id, "date": w.date.isoformat(), "target_tss": w.target_tss, "zone": w.zone, "notes": w.notes}
            for w in all_planned
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
    """Story 12 compile branch: turn a block's authored intent into concrete
    planned workouts. Scope is set by the athlete's message -- one day
    ("a session for Thursday", 12a) or one week ("fill in week 3" / "the base
    block" / "the next week", 12b). Either way the result is capped to a
    single plan-block week in code. Returns {"summary": str, "changes": [...]}
    guardrail-filtered, or None if the coach isn't configured.

    Writes nothing -- the returned changes ride the shared propose-confirm-
    write flow (coach_conversation._propose_and_log), applied only on
    confirmation by coach_plan_adjust.apply_changes."""
    today = datetime.now(LOCAL_TZ).date()
    context = build_compile_context(db, today)

    prompt = (
        f'The athlete asked you to compile concrete workouts: "{message_text}"\n\n'
        "Here is the block plan and current calendar:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nWork out the scope from their message:\n"
        "- A single day ('a session for Thursday', 'what should I do today') -> "
        "propose ONE session for that day (default to today if unclear).\n"
        "- A single named week ('fill in week 3', 'compile this week') -> propose "
        "that week's sessions.\n"
        "- A whole block or 'the next week'/'continue' ('fill in the base block') -> "
        "propose sessions for the FIRST week of that block that still has "
        "planned_workout_count 0 (or the earliest un-filled week overall for "
        "'next'/'continue'), and end your summary by inviting them to say 'the next "
        "week' to keep going.\n\n"
        "Never propose more than ONE week's worth of sessions in a single reply -- "
        "that is non-negotiable; the athlete approves one week at a time. Compile "
        "from the block's focus/detail, honor the standing constraints (especially "
        "rides-per-week and rest days -- do not over-fill a week), and fit target_tss "
        "and zone to recent load. Use 'create' for new days; use 'update' only for a "
        "day that already has a workout, with its id from planned_workouts. Every date "
        "must be strictly before guardrail_hard_boundary (never on or after it). If "
        "nothing should be added (e.g. the week is already full, or it's past the "
        "guardrail), return an empty changes list and explain why in summary."
    )
    result = ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, PROPOSAL_SCHEMA)
    if not result:
        return None

    valid_ids = {w["id"] for w in context["planned_workouts"]}
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

    safe_changes = _restrict_to_one_week(context["blocks"], safe_changes)
    return {"summary": result.get("summary", ""), "changes": safe_changes}
