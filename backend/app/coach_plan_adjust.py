import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import ai_coach, plan_blocks, plan_constraints, race_goal
from .coach_voice import COACH_SYSTEM_PROMPT
from .models import DailyReadiness, PlannedWorkout, RideSummary

LOCAL_TZ = dt_timezone(timedelta(hours=9))
RECENT_RIDE_DAYS = 7

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["disruption", "plan_structure", "generic"],
            "description": "'disruption' only if the athlete is reporting something that affects their near-term ability to train as planned (illness, injury, travel, missed days, schedule change). 'plan_structure' if they're asking to change the overall block plan itself -- phase, focus, or week-level structure (e.g. 'make week 3 a recovery week', 'push more threshold in the build phase'). 'generic' for anything else, including subjective check-in numbers or small talk.",
        },
    },
    "required": ["intent"],
    "additionalProperties": False,
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["confirm", "reject", "unclear"],
            "description": "Whether this reply clearly confirms applying the proposed change, clearly rejects it, or is ambiguous.",
        },
    },
    "required": ["decision"],
    "additionalProperties": False,
}

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Short, plain-language explanation of the proposed change (or why nothing needs to change), sent directly to the athlete.",
        },
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["update", "delete", "create"]},
                    "workout_id": {
                        "type": ["integer", "null"],
                        "description": "Required for update/delete -- must be one of the ids given in editable_planned_workouts. Null for create.",
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "target_tss": {"type": ["number", "null"]},
                    "zone": {"type": ["string", "null"], "description": "z1-z5 or null"},
                    "notes": {"type": ["string", "null"]},
                },
                "required": ["action", "workout_id", "date", "target_tss", "zone", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}


def classify_message_intent(text: str) -> str:
    result = ai_coach.ask_claude_structured(
        f'The athlete just sent: "{text}"\n\nClassify its intent.',
        COACH_SYSTEM_PROMPT,
        INTENT_SCHEMA,
    )
    # Unconfigured or unparsable -> never guess disruption; worst case is a
    # message that deserved a proposal just gets logged as a plain check-in.
    return result.get("intent", "generic")


def classify_proposal_reply(text: str) -> str:
    result = ai_coach.ask_claude_structured(
        f'The athlete was asked to confirm a proposed plan change and replied: "{text}"\n\nClassify their reply.',
        COACH_SYSTEM_PROMPT,
        REPLY_SCHEMA,
    )
    # Unconfigured or unparsable -> never silently write (principle 4).
    return result.get("decision", "unclear")


def _hard_boundary(db: Session) -> date:
    """The one non-negotiable line: taper week (if the plan has one) or the
    event date itself, whichever comes first. No proposed or confirmed
    change may land on or after this date, no matter what the model says."""
    event_date = datetime.strptime(race_goal.get_goal(db)["date"], "%Y-%m-%d").date()
    taper = plan_blocks.taper_week(db)
    if taper is not None:
        return min(datetime.strptime(taper["start"], "%Y-%m-%d").date(), event_date)
    return event_date


def _current_week(db: Session, today: date):
    return plan_blocks.current_block(db, today)


def _recent_rides(db: Session, today: date) -> list:
    cutoff_local = datetime.combine(
        today - timedelta(days=RECENT_RIDE_DAYS), datetime.min.time(), tzinfo=LOCAL_TZ
    )
    rides = (
        db.query(RideSummary)
        .filter(RideSummary.start_date >= cutoff_local)
        .order_by(RideSummary.start_date)
        .all()
    )
    return [
        {
            "date": r.start_date.astimezone(LOCAL_TZ).date().isoformat(),
            "name": r.name,
            "tss": round(r.ride_tss, 1) if r.ride_tss else None,
        }
        for r in rides
    ]


def build_disruption_context(db: Session, today: date):
    current_week = _current_week(db, today)
    if current_week is None:
        return None

    week_end = datetime.strptime(current_week["end"], "%Y-%m-%d").date()
    planned = (
        db.query(PlannedWorkout)
        .filter(PlannedWorkout.date >= today, PlannedWorkout.date <= week_end)
        .order_by(PlannedWorkout.date)
        .all()
    )
    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()

    return {
        "today": today.isoformat(),
        "current_week": {
            "week": current_week["week"],
            "label": current_week["label"],
            "focus": current_week["focus"],
            "start": current_week["start"],
            "end": current_week["end"],
        },
        "editable_planned_workouts": [
            {"id": w.id, "date": w.date.isoformat(), "target_tss": w.target_tss, "zone": w.zone, "notes": w.notes}
            for w in planned
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


def propose_adjustment(db: Session, message_text: str):
    """Returns {"summary": str, "changes": [...]} with changes already
    guardrail-filtered, or None if there's no active plan week to adjust
    or the coach isn't configured."""
    today = datetime.now(LOCAL_TZ).date()
    context = build_disruption_context(db, today)
    if context is None:
        return None

    prompt = (
        f'The athlete just said: "{message_text}"\n\n'
        "Here is the current state of the plan for this week:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nPropose concrete changes to editable_planned_workouts to handle this "
        "disruption -- only using the workout ids given, only for dates strictly "
        "before guardrail_hard_boundary (never on or after it -- that line is "
        "absolutely non-negotiable). If nothing needs to change, return an empty "
        "changes list and explain why in summary."
    )
    result = ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, PROPOSAL_SCHEMA)
    if not result:
        return None

    valid_ids = {w["id"] for w in context["editable_planned_workouts"]}
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

    return {"summary": result.get("summary", ""), "changes": safe_changes}


def apply_changes(db: Session, changes: list) -> int:
    """Writes accepted changes to planned_workouts. Re-checks the guardrail
    at apply time too, in case time passed between proposing and confirming."""
    hard_boundary = _hard_boundary(db)
    applied = 0
    for change in changes:
        try:
            change_date = datetime.strptime(change["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if change_date >= hard_boundary:
            continue

        action = change.get("action")
        if action in ("update", "delete"):
            row = db.query(PlannedWorkout).filter(PlannedWorkout.id == change.get("workout_id")).first()
            if row is None:
                continue
            if action == "delete":
                db.delete(row)
            else:
                row.date = change_date
                row.target_tss = change.get("target_tss")
                row.zone = change.get("zone")
                row.notes = change.get("notes")
            applied += 1
        elif action == "create":
            db.add(
                PlannedWorkout(
                    date=change_date,
                    target_tss=change.get("target_tss"),
                    zone=change.get("zone"),
                    notes=change.get("notes"),
                )
            )
            applied += 1

    db.commit()
    return applied
