import re
from datetime import datetime
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import coach_plan_adjust, coach_plan_structure, coach_qa
from .activity_log import log_event
from .models import IntegrationLog, PlanAdjustmentProposal

GENERIC_REPLY = (
    "That doesn't look like a plan change, a disruption, or a question about "
    "your data -- try describing what happened, asking about your training, "
    "or what you'd like to adjust."
)

# Everything that counts as a message in the one unified coach conversation
# -- proactive pushes (their full sent text is already logged) and reactive
# exchanges (disruption/plan-structure/Q&A), mirrored identically on
# Telegram and the dashboard's "Talk to your coach" thread.
COACH_EVENTS = {
    "verdict_sent",
    "ride_debrief_sent",
    "missed_workout_sent",
    "weekly_summary_sent",
    "constraint_drift_sent",
    "plan_thread_coach",
}
ATHLETE_EVENTS = {"checkin_received"}

# Generic "key=value | text" prefix used to correlate a logged message back
# to what it's about (a ride, a date, a week, a proposal) without it being
# part of the displayed text.
_MARKER_RE = re.compile(r"^(\w+)=(\S+) \| (.*)$", re.DOTALL)


def _strip_marker(summary: str):
    match = _MARKER_RE.match(summary or "")
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, summary or ""


def echo_athlete_action(source: str, notify_telegram: bool, text: str) -> None:
    """Telegram's Bot API can't make a message appear as if the athlete
    sent it -- a bot can only send its own messages. So when the athlete
    writes from a surface other than Telegram, echo what they said into
    the chat before the coach's reply, so the conversation still reads
    coherently there. A no-op for messages that originated on Telegram
    itself, since they're already visible in that chat."""
    if notify_telegram and source != "telegram":
        from . import telegram

        telegram.send_message(f"\U0001F4DD (from dashboard) {text}")


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


def _answer_and_log(db: Session, source: str, question: str, notify_telegram: bool) -> dict:
    from . import telegram

    recent = get_thread(db, limit=20)
    answer = coach_qa.answer_question(db, question, recent)
    if not answer:
        answer = "Sorry, I couldn't work that out just now -- the coach may not be configured."

    if notify_telegram:
        telegram.send_message(answer)
    log_event(db, source, "plan_thread_coach", answer)
    return {"answer": answer}


def handle_athlete_message(db: Session, source: str, text: str, notify_telegram: bool, respond_to_generic: bool = False) -> dict:
    """One coach brain behind every surface. `source` is just which channel
    the message came in on ('telegram' or 'dashboard') -- the reasoning
    doesn't know or care. Three grounded reasoning tasks share one voice and
    one thread: disruption/plan_structure read their own narrow context and
    may propose a calendar change (propose-confirm-write); question is
    read-only, answered from coach_context's broader data plus recent
    thread history.

    `respond_to_generic` is the one real behavioral difference between
    surfaces: on Telegram, a generic message (numbers, small talk) stays
    silent like it always has -- this isn't the only thing Telegram is for.
    On the dashboard's dedicated "Talk to your coach" box, every message is
    presumed relevant, so a generic classification still gets a clarifying
    reply.
    """
    # Telegram already logs the raw message via process_update before this
    # is ever called -- logging it again here would duplicate the bubble.
    if source != "telegram":
        log_event(db, source, "checkin_received", text[:500])
    echo_athlete_action(source, notify_telegram, text)

    intent = coach_plan_adjust.classify_message_intent(text)

    if intent == "disruption":
        return _propose_and_log(db, source, text, coach_plan_adjust.propose_adjustment, "workout", notify_telegram)

    if intent == "plan_structure":
        return _propose_and_log(db, source, text, coach_plan_structure.propose_structure_change, "block", notify_telegram)

    if intent == "question":
        return _answer_and_log(db, source, text, notify_telegram)

    if respond_to_generic:
        from . import telegram

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


def get_thread(db: Session, limit: int = 80) -> list:
    rows = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.event.in_(COACH_EVENTS | ATHLETE_EVENTS))
        .order_by(IntegrationLog.created_at.desc(), IntegrationLog.id.desc())
        .limit(limit)
        .all()
    )

    entries = []
    for row in reversed(rows):
        key, value, text = _strip_marker(row.summary)
        role = "athlete" if row.event in ATHLETE_EVENTS else "coach"
        entry = {"role": role, "text": text, "timestamp": row.created_at.isoformat(), "source": row.source}
        if role == "coach" and key == "proposal_id":
            proposal = db.query(PlanAdjustmentProposal).filter(PlanAdjustmentProposal.id == int(value)).first()
            if proposal is not None:
                entry["proposal"] = {"id": proposal.id, "status": proposal.status, "kind": proposal.kind}
        entries.append(entry)

    return entries
