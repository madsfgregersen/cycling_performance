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

# Same shape as the disruption proposal (so coach_plan_adjust.apply_changes
# writes it unchanged), plus continue_block: the athlete's scope signal that
# drives week-by-week auto-advance on confirmation.
COMPILE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": PROPOSAL_SCHEMA["properties"]["summary"],
        "continue_block": {
            "type": "boolean",
            "description": (
                "true if the athlete asked to fill a whole block/phase or to continue/'next' "
                "(enables rolling through the block one approved week at a time). false for a single "
                "day or a single explicitly-named week ('compile week 3') -- those don't auto-advance."
            ),
        },
        "changes": PROPOSAL_SCHEMA["properties"]["changes"],
    },
    "required": ["summary", "continue_block", "changes"],
    "additionalProperties": False,
}


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


def _planned_counts_by_week(db: Session, blocks: list) -> dict:
    counts = {}
    for w in db.query(PlannedWorkout).all():
        week = _week_of(blocks, w.date)
        if week is not None:
            counts[week] = counts.get(week, 0) + 1
    return counts


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
    counts = _planned_counts_by_week(db, blocks)

    return {
        "today": today.isoformat(),
        "current_block": plan_blocks.current_block(db, today),
        # Per-week focus plus how many sessions are already scheduled, so the
        # coach can pick the first un-filled week of a block on its own.
        "blocks": [{**b, "planned_workout_count": counts.get(b["week"], 0)} for b in blocks],
        "planned_workouts": [
            {"id": w.id, "date": w.date.isoformat(), "target_tss": w.target_tss, "zone": w.zone, "title": w.title, "notes": w.notes}
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


def _compile_core(db: Session, message_text: str):
    """Shared compile reasoning: one LLM call + guardrail + one-week cap.
    Returns {"summary", "changes", "continue_block"} or None if the coach
    isn't configured. Used both for a fresh request and for each auto-advanced
    week in a block fill."""
    today = datetime.now(LOCAL_TZ).date()
    context = build_compile_context(db, today)

    prompt = (
        f'The athlete asked you to compile concrete workouts: "{message_text}"\n\n'
        "Here is the block plan and current calendar:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nWork out the scope from their message:\n"
        "- A single day ('a session for Thursday', 'what should I do today') -> "
        "propose ONE session for that day (default to today if unclear); set "
        "continue_block false.\n"
        "- A single named week ('fill in week 3', 'compile this week') -> propose "
        "that week's sessions; set continue_block false.\n"
        "- A whole block or 'the next week'/'continue' ('fill in the base block') -> "
        "propose sessions for the FIRST week of that block that still has "
        "planned_workout_count 0 (or the earliest un-filled week overall for "
        "'next'/'continue'); set continue_block true.\n\n"
        "Never propose more than ONE week's worth of sessions in a single reply -- "
        "that is non-negotiable; the athlete approves one week at a time. Compile "
        "from the block's focus/detail, honor the standing constraints (especially "
        "rides-per-week and rest days -- do not over-fill a week), and fit target_tss "
        "and zone to recent load. Give every session a SHORT title (a few words, e.g. "
        "'Z2 long ride', 'Threshold 2x20', 'Hill reps', 'Recovery spin') and put the "
        "full workout detail in notes -- the title is the calendar label, not the "
        "description. Use 'create' for new days; use 'update' only for a "
        "day that already has a workout, with its id from planned_workouts. Every date "
        "must be strictly before guardrail_hard_boundary (never on or after it). If "
        "nothing should be added (e.g. the week is already full, or it's past the "
        "guardrail), return an empty changes list and explain why in summary."
    )
    result = ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, COMPILE_SCHEMA)
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
    return {
        "summary": result.get("summary", ""),
        "changes": safe_changes,
        "continue_block": bool(result.get("continue_block")),
    }


def propose_compilation(db: Session, message_text: str):
    """Story 12 compile branch: turn a block's authored intent into concrete
    planned workouts. Scope is set by the athlete's message -- one day
    ("a session for Thursday", 12a) or one week ("fill in week 3" / "the base
    block" / "the next week", 12b), capped to a single plan-block week.
    Returns {"summary", "changes", "kind"} or None if the coach isn't
    configured; kind "compile_block" (auto-advancing block fill) or "compile"
    (a one-off day/week). Writes nothing -- rides the shared propose-confirm-
    write flow, applied on confirmation by coach_plan_adjust.apply_changes."""
    core = _compile_core(db, message_text)
    if core is None:
        return None
    kind = "compile_block" if (core["continue_block"] and core["changes"]) else "compile"
    return {"summary": core["summary"], "changes": core["changes"], "kind": kind}


def propose_next_in_block(db: Session, prev_changes: list):
    """Auto-advance: after a confirmed block-compile week, compile the next
    un-filled week of the SAME block (phase) so the athlete rolls through it
    one approved week at a time. Bounds a block fill to that block -- when the
    phase is complete, returns None and the chain stops (the full-plan sweep
    is story 12c's deliberate, separate scope). Returns {"summary", "changes"}
    for a fresh proposal, or None if there's no next week or the coach isn't
    configured."""
    blocks = plan_blocks.list_blocks(db)

    prev_week = None
    for change in prev_changes:
        try:
            prev_week = _week_of(blocks, datetime.strptime(change["date"], "%Y-%m-%d").date())
        except (KeyError, ValueError, TypeError):
            continue
        if prev_week is not None:
            break
    if prev_week is None:
        return None

    prev = next((b for b in blocks if b["week"] == prev_week), None)
    if prev is None:
        return None
    phase = prev["phase"]

    hard_boundary = _hard_boundary(db)
    counts = _planned_counts_by_week(db, blocks)
    candidates = sorted(
        (
            b
            for b in blocks
            if b["phase"] == phase
            and b["week"] > prev_week
            and counts.get(b["week"], 0) == 0
            and datetime.strptime(b["start"], "%Y-%m-%d").date() < hard_boundary
        ),
        key=lambda b: b["week"],
    )
    if not candidates:
        return None

    target = candidates[0]["week"]
    core = _compile_core(db, f"Compile week {target} of the plan.")
    if core is None or not core["changes"]:
        return None
    return {"summary": core["summary"], "changes": core["changes"]}


TITLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": (
                "A short calendar label of a few words for this session, drawn from its detail -- "
                "e.g. 'Z2 long ride', 'Threshold 2x20', 'Hill reps', 'Recovery spin'."
            ),
        },
    },
    "required": ["title"],
    "additionalProperties": False,
}


def _title_from_notes(notes: str, zone) -> str:
    """Derive a short card title from an existing workout's detail. Returns ''
    if the coach isn't configured (caller then leaves the row's title unset)."""
    result = ai_coach.ask_claude_structured(
        f'A planned cycling workout (zone {zone or "n/a"}) has this detail:\n\n"{notes}"\n\n'
        "Give it a short calendar label.",
        COACH_SYSTEM_PROMPT,
        TITLE_SCHEMA,
        max_tokens=64,
    )
    return (result.get("title") or "").strip()


def backfill_titles(db: Session) -> dict:
    """One-off: give a short title to existing planned workouts that have
    detail in notes but no title yet (created before the title/notes split).
    Idempotent -- only touches rows with a null/blank title and non-blank
    notes, so re-running is a no-op once every row has a title."""
    rows = (
        db.query(PlannedWorkout)
        .filter((PlannedWorkout.title.is_(None)) | (PlannedWorkout.title == ""))
        .order_by(PlannedWorkout.date)
        .all()
    )
    updated = 0
    skipped = 0
    for row in rows:
        if not (row.notes or "").strip():
            skipped += 1
            continue
        title = _title_from_notes(row.notes, row.zone)
        if not title:
            skipped += 1
            continue
        row.title = title
        updated += 1
    db.commit()
    return {"updated": updated, "skipped": skipped, "candidates": len(rows)}
