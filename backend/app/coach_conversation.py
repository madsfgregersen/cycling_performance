import re
from datetime import datetime
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import coach_plan_adjust, coach_plan_structure
from .activity_log import log_event
from .models import IntegrationLog, PlanAdjustmentProposal

GENERIC_REPLY = (
    "That doesn't look like a plan change or a disruption to react to -- "
    "try describing what happened, or what you'd like to adjust."
)

_MARKER_RE = re.compile(r"^proposal_id=(\d+) \| (.*)$", re.DOTALL)


def _parse_coach_summary(summary: str):
    match = _MARKER_RE.match(summary or "")
    if match:
        return int(match.group(1)), match.group(2)
    return None, summary


def _propose_and_log(db: Session, source: str, message_text: str, propose_fn, kind: str, notify_telegram: bool) -> dict:
    from . import telegram  # local import -- telegram.py imports this module

    proposal = propose_fn(db, message_text)
    if proposal is None:
        log_event(db, source, "plan_thread_coach", "Sorry, I couldn't work out a proposal for that -- the coach may not be configured.")
        return {"proposal": None, "reason": "coach unavailable"}

    if not proposal["changes"]:
        log_event(db, source, "plan_thread_coach", proposal["summary"])
        if notify_telegram:
            telegram.send_message(proposal["summary"])
        return {"proposal": None, "summary": proposal["summary"]}

    row = PlanAdjustmentProposal(
        trigger_message=message_text,
        proposal_summary=proposal["summary"],
        changes=proposal["changes"],
        status="pending",
        kind=kind,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if notify_telegram:
        coach_text = f"{proposal['summary']}\n\nReply YES to apply this, or tell me what you'd rather do instead."
        telegram.send_message(coach_text)
    else:
        coach_text = proposal["summary"]

    log_event(db, source, "plan_thread_coach", f"proposal_id={row.id} | {coach_text}")
    return {"proposal": {"id": row.id, "summary": row.proposal_summary, "changes": row.changes, "kind": row.kind}}


def handle_athlete_message(db: Session, source: str, text: str, notify_telegram: bool, respond_to_generic: bool = False) -> dict:
    """One coach brain behind every surface. `source` is just which channel
    the message came in on ('telegram' or 'dashboard') -- the reasoning
    (coach_plan_adjust / coach_plan_structure) doesn't know or care.

    `respond_to_generic` is the one real behavioral difference between
    surfaces: on Telegram, a generic message (numbers, small talk) should
    stay silent like it always has -- this page isn't the only thing
    Telegram is for. On the dashboard's dedicated "Adjust with coach" page,
    every message sent there is presumed plan-related, so a generic
    classification still gets a clarifying reply.
    """
    intent = coach_plan_adjust.classify_message_intent(text)

    if intent == "disruption":
        log_event(db, source, "plan_thread_athlete", text[:500])
        return _propose_and_log(db, source, text, coach_plan_adjust.propose_adjustment, "workout", notify_telegram)

    if intent == "plan_structure":
        log_event(db, source, "plan_thread_athlete", text[:500])
        return _propose_and_log(db, source, text, coach_plan_structure.propose_structure_change, "block", notify_telegram)

    if respond_to_generic:
        from . import telegram

        log_event(db, source, "plan_thread_athlete", text[:500])
        log_event(db, source, "plan_thread_coach", GENERIC_REPLY)
        if notify_telegram:
            telegram.send_message(GENERIC_REPLY)
        return {"proposal": None, "intent": "generic", "reply": GENERIC_REPLY}

    return {"proposal": None, "intent": "generic"}


def resolve_proposal(db: Session, proposal: PlanAdjustmentProposal, decision: str, source: str, notify_telegram: bool) -> dict:
    from . import telegram

    marker = f"proposal_id={proposal.id}"

    if decision == "confirm":
        if proposal.kind == "block":
            applied = coach_plan_structure.apply_block_changes(db, proposal.changes)
            noun = "block(s)"
        else:
            applied = coach_plan_adjust.apply_changes(db, proposal.changes)
            noun = "workout(s)"
        proposal.status = "confirmed"
        proposal.resolved_at = datetime.now(dt_timezone.utc)
        db.commit()
        reply = f"Done — updated {applied} {noun}."
        result = {"applied": applied}
    elif decision == "reject":
        proposal.status = "rejected"
        proposal.resolved_at = datetime.now(dt_timezone.utc)
        db.commit()
        reply = "No problem — left your plan as is."
        result = {"rejected": True}
    else:
        reply = "Just to confirm — want me to apply that change? (yes/no)"
        result = {"unclear": True}

    if notify_telegram:
        telegram.send_message(reply)
    log_event(db, source, "plan_thread_coach", f"{marker} | {reply}")
    return result


def get_thread(db: Session, limit: int = 50) -> list:
    rows = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.event.in_(["plan_thread_athlete", "plan_thread_coach"]))
        .order_by(IntegrationLog.created_at.desc(), IntegrationLog.id.desc())
        .limit(limit)
        .all()
    )

    entries = []
    for row in reversed(rows):
        if row.event == "plan_thread_athlete":
            entries.append(
                {"role": "athlete", "text": row.summary, "timestamp": row.created_at.isoformat(), "source": row.source}
            )
            continue

        proposal_id, text = _parse_coach_summary(row.summary or "")
        entry = {"role": "coach", "text": text, "timestamp": row.created_at.isoformat(), "source": row.source}
        if proposal_id is not None:
            proposal = db.query(PlanAdjustmentProposal).filter(PlanAdjustmentProposal.id == proposal_id).first()
            if proposal is not None:
                entry["proposal"] = {"id": proposal.id, "status": proposal.status, "kind": proposal.kind}
        entries.append(entry)

    return entries
