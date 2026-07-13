import json

from sqlalchemy.orm import Session

from . import ai_coach, plan_blocks, race_goal
from .coach_voice import COACH_SYSTEM_PROMPT

STRUCTURE_PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Short, plain-language explanation of the proposed structure change (or why nothing should change), sent directly to the athlete.",
        },
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "week": {
                        "type": "integer",
                        "description": "Must be one of the existing week numbers given -- never the taper week, never a new week.",
                    },
                    "phase": {"type": ["string", "null"], "description": "e.g. build/recovery/specificity -- null to leave unchanged."},
                    "label": {"type": ["string", "null"]},
                    "focus": {"type": ["string", "null"]},
                    "detail": {"type": ["string", "null"]},
                },
                "required": ["week", "phase", "label", "focus", "detail"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}


def build_structure_context(db: Session) -> dict:
    return {"goal": race_goal.get_goal(db), "blocks": plan_blocks.list_blocks(db)}


def propose_structure_change(db: Session, message_text: str):
    """Returns {"summary": str, "changes": [...]} with changes already
    guardrail-filtered (never the taper week, never an unknown week
    number), or None if the coach isn't configured."""
    context = build_structure_context(db)
    taper = next((b for b in context["blocks"] if b["phase"] == "taper"), None)
    taper_week_num = taper["week"] if taper else None

    prompt = (
        f'The athlete wants to adjust the plan structure: "{message_text}"\n\n'
        "Here is the current block plan:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nPropose changes to the qualitative fields (phase/label/focus/detail) "
        "of existing weeks only -- never change week numbers or dates, and never "
        f"touch week {taper_week_num} (the taper/race week, absolutely "
        "non-negotiable). Leave a field null if it shouldn't change. If nothing "
        "should change, return an empty changes list and explain why in summary."
    )
    result = ai_coach.ask_claude_structured(prompt, COACH_SYSTEM_PROMPT, STRUCTURE_PROPOSAL_SCHEMA)
    if not result:
        return None

    valid_weeks = {b["week"] for b in context["blocks"] if b["phase"] != "taper"}
    safe_changes = [c for c in result.get("changes", []) if c.get("week") in valid_weeks]

    return {"summary": result.get("summary", ""), "changes": safe_changes}


def apply_block_changes(db: Session, changes: list) -> int:
    """Writes accepted changes to plan_blocks. Re-checks the guardrail at
    apply time too, same reasoning as coach_plan_adjust.apply_changes."""
    taper = plan_blocks.taper_week(db)
    taper_week_num = taper["week"] if taper else None

    applied = 0
    for change in changes:
        week = change.get("week")
        if week is None or week == taper_week_num:
            continue
        updated = plan_blocks.update_block(
            db,
            week,
            phase=change.get("phase"),
            label=change.get("label"),
            focus=change.get("focus"),
            detail=change.get("detail"),
        )
        if updated:
            applied += 1
    return applied
