import json
import os
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import httpx
from sqlalchemy.orm import Session

from . import (
    coach_constraint_drift,
    coach_conversation,
    coach_missed_workout,
    coach_morning,
    coach_plan_adjust,
    coach_ride,
    coach_weekly_summary,
    messaging_settings,
)
from .activity_log import log_event
from .models import DailyReadiness, IntegrationLog, PlanAdjustmentProposal, TelegramCheckin

ASK_SUBJECTIVE = (
    'How fresh do you feel today, and how\'s work/life stress? '
    'Reply with two numbers 1-5 (e.g. "4, 2").'
)

ASK_RIDE_FEEL = (
    'How did that one feel? RPE and any notes (e.g. "7/10, legs a bit heavy").'
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Personal single-user app; matches the local timezone used elsewhere
# (dashboard.py) for bucketing events into calendar days.
LOCAL_TZ = dt_timezone(timedelta(hours=9))


def send_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        response = httpx.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def set_webhook(callback_url: str) -> dict:
    response = httpx.post(
        f"{API_BASE}/setWebhook",
        json={"url": callback_url, "secret_token": TELEGRAM_WEBHOOK_SECRET},
        timeout=15,
    )
    return {"status_code": response.status_code, "body": response.json()}


def get_webhook_info() -> dict:
    response = httpx.get(f"{API_BASE}/getWebhookInfo", timeout=15)
    return {"status_code": response.status_code, "body": response.json()}


def _verdict_emoji(verdict: str) -> str:
    return {"green": "\U0001F7E2", "amber": "\U0001F7E0", "red": "\U0001F534"}.get(
        verdict, "⚪"
    )


def _already_sent_today(db: Session) -> bool:
    today_local = datetime.now(LOCAL_TZ).date()
    recent = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.source == "telegram", IntegrationLog.event == "verdict_sent")
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    if recent is None or recent.created_at is None:
        return False
    return recent.created_at.astimezone(LOCAL_TZ).date() == today_local


def send_morning_verdict(db: Session) -> dict:
    if not messaging_settings.is_enabled(db, "morning_verdict"):
        return {"sent": False, "reason": "disabled in messaging settings"}

    if _already_sent_today(db):
        return {"sent": False, "reason": "already sent today"}

    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()
    if latest is None:
        log_event(db, "telegram", "verdict_skipped", "no readiness data yet")
        return {"sent": False, "reason": "no data"}

    explanation = coach_morning.explain_verdict(db)
    emoji = _verdict_emoji(latest.verdict)

    if explanation:
        # Cache this morning's structured brief so the dashboard's Now page
        # can show the coach's read without making its own live LLM call.
        # Reuses the integration log -- no new table, no migration.
        log_event(
            db,
            "coach",
            "morning_brief",
            json.dumps(
                {
                    "date": latest.date.isoformat(),
                    "headline": explanation.get("headline", ""),
                    "why": explanation.get("why", ""),
                    "note": explanation.get("note", ""),
                }
            ),
        )
        text = (
            f"{emoji} {explanation['headline']}\n\n"
            f"{explanation['why']}\n\n"
            f"{explanation['note']}\n\n"
            f"{ASK_SUBJECTIVE}"
        ).strip()
    else:
        # Fallback if the coach call isn't configured or fails -- the
        # original plain verdict message, so the morning message never
        # just goes silent.
        text = (
            f"{emoji} Morning readiness: {(latest.verdict or 'unknown').capitalize()}\n"
            f"TSB {latest.tsb:+.1f} · CTL {latest.ctl:.1f} · ATL {latest.atl:.1f}\n"
            f"As of {latest.date.isoformat()}\n\n"
            f"{ASK_SUBJECTIVE}"
        )

    sent = send_message(text)
    log_event(db, "telegram", "verdict_sent" if sent else "verdict_send_failed", text)
    return {"sent": sent, "coach_explained": bool(explanation)}


def _already_logged(db: Session, event: str, marker: str) -> bool:
    return (
        db.query(IntegrationLog)
        .filter(IntegrationLog.source == "telegram", IntegrationLog.event == event)
        .filter(IntegrationLog.summary.like(f"%{marker}%"))
        .first()
        is not None
    )


def _send_explanation(db: Session, explanation: dict) -> tuple:
    text = f"{explanation['headline']}\n\n{explanation['why']}"
    if explanation.get("note"):
        text += f"\n\n{explanation['note']}"
    sent = send_message(text)
    return sent, text


def send_post_ride_debrief(db: Session, ride) -> dict:
    # Debrief text (story 3) and the feel/RPE ask (story 4) are independent
    # toggles -- either can run without the other, or neither, in which case
    # nothing gets sent for this ride at all.
    debrief_enabled = messaging_settings.is_enabled(db, "post_ride_debrief")
    ask_enabled = messaging_settings.is_enabled(db, "ride_feel_ask")
    if not debrief_enabled and not ask_enabled:
        return {"sent": False, "reason": "disabled in messaging settings"}

    marker = f"ride_id={ride.id}"
    if _already_logged(db, "ride_debrief_sent", marker):
        return {"sent": False, "reason": "already sent for this ride"}

    parts = []
    explanation = None
    if debrief_enabled:
        explanation = coach_ride.explain_ride(db, ride)
        if explanation:
            part = f"{explanation['headline']}\n\n{explanation['why']}"
            if explanation.get("note"):
                part += f"\n\n{explanation['note']}"
            parts.append(part)
        else:
            log_event(db, "telegram", "ride_debrief_skipped", f"{marker} | coach not configured")

    if ask_enabled:
        parts.append(ASK_RIDE_FEEL)

    if not parts:
        return {"sent": False, "reason": "coach unavailable"}

    text = "\n\n".join(parts)
    sent = send_message(text)
    log_event(
        db,
        "telegram",
        "ride_debrief_sent" if sent else "ride_debrief_send_failed",
        f"{marker} | {text}",
    )
    if sent and ask_enabled:
        log_event(db, "telegram", "ride_feel_ask_sent", marker)
    return {"sent": sent, "coach_explained": bool(explanation)}


def send_missed_workout_nudge(db: Session) -> dict:
    if not messaging_settings.is_enabled(db, "missed_workout_nudge"):
        return {"sent": False, "reason": "disabled in messaging settings"}

    checked_date = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
    context = coach_missed_workout.build_missed_workout_context(db, checked_date)
    if context is None:
        return {"sent": False, "reason": "nothing missed"}

    marker = f"date={checked_date.isoformat()}"
    if _already_logged(db, "missed_workout_sent", marker):
        return {"sent": False, "reason": "already sent for this date"}

    explanation = coach_missed_workout.explain_missed_workout(db, context)
    if not explanation:
        log_event(db, "telegram", "missed_workout_skipped", f"{marker} | coach not configured")
        return {"sent": False, "reason": "coach unavailable"}

    sent, text = _send_explanation(db, explanation)
    log_event(
        db,
        "telegram",
        "missed_workout_sent" if sent else "missed_workout_send_failed",
        f"{marker} | {text}",
    )
    return {"sent": sent}


def send_weekly_summary(db: Session) -> dict:
    if not messaging_settings.is_enabled(db, "weekly_summary"):
        return {"sent": False, "reason": "disabled in messaging settings"}

    today_local = datetime.now(LOCAL_TZ).date()
    week = coach_weekly_summary.find_week_ending_yesterday(db, today_local)
    if week is None:
        return {"sent": False, "reason": "no week boundary today"}

    marker = f"week={week['week']}"
    if _already_logged(db, "weekly_summary_sent", marker):
        return {"sent": False, "reason": "already sent for this week"}

    context = coach_weekly_summary.build_weekly_context(db, week)
    explanation = coach_weekly_summary.explain_week(db, context)
    if not explanation:
        log_event(db, "telegram", "weekly_summary_skipped", f"{marker} | coach not configured")
        return {"sent": False, "reason": "coach unavailable"}

    sent, text = _send_explanation(db, explanation)
    log_event(
        db,
        "telegram",
        "weekly_summary_sent" if sent else "weekly_summary_send_failed",
        f"{marker} | {text}",
    )
    return {"sent": sent}


def send_constraint_drift_alert(db: Session) -> dict:
    if not messaging_settings.is_enabled(db, "constraint_drift_alert"):
        return {"sent": False, "reason": "disabled in messaging settings"}

    today_local = datetime.now(LOCAL_TZ).date()
    marker = f"date={today_local.isoformat()}"
    if _already_logged(db, "constraint_drift_sent", marker):
        return {"sent": False, "reason": "already checked today"}

    context = coach_constraint_drift.build_drift_context(db)
    if context is None:
        return {"sent": False, "reason": "no active constraints"}

    explanation = coach_constraint_drift.explain_drift(db, context)
    if not explanation:
        log_event(db, "telegram", "constraint_drift_skipped", f"{marker} | coach not configured")
        return {"sent": False, "reason": "coach unavailable"}

    if not explanation.get("drifted"):
        log_event(db, "telegram", "constraint_drift_checked", f"{marker} | no drift")
        return {"sent": False, "reason": "no drift"}

    sent, text = _send_explanation(db, explanation)
    log_event(
        db,
        "telegram",
        "constraint_drift_sent" if sent else "constraint_drift_send_failed",
        f"{marker} | {text}",
    )
    return {"sent": sent}


def _pending_ride_feel_ask(db: Session):
    """Return the ride_id an incoming reply is most likely answering, or
    None. Telegram replies here aren't threaded to a specific message, so --
    same rule the morning check-in already relies on -- whichever question
    was asked most recently is assumed to be what the next message answers."""
    latest_ask = (
        db.query(IntegrationLog)
        .filter(
            IntegrationLog.source == "telegram",
            IntegrationLog.event.in_(["verdict_sent", "ride_feel_ask_sent"]),
        )
        # id as a tiebreaker -- created_at alone isn't fine-grained enough to
        # order two events landing in the same instant.
        .order_by(IntegrationLog.created_at.desc(), IntegrationLog.id.desc())
        .first()
    )
    if latest_ask is None or latest_ask.event != "ride_feel_ask_sent":
        return None

    ride_id = int(latest_ask.summary.split("ride_id=")[1])
    if _already_logged(db, "ride_feel_answered", f"ride_id={ride_id}"):
        return None
    return ride_id


def _pending_proposal(db: Session):
    return (
        db.query(PlanAdjustmentProposal)
        .filter(PlanAdjustmentProposal.status == "pending")
        .order_by(PlanAdjustmentProposal.created_at.desc(), PlanAdjustmentProposal.id.desc())
        .first()
    )


def process_update(db: Session, update: dict) -> dict:
    message = update.get("message") or update.get("edited_message")
    if message is None:
        return {"handled": False, "reason": "no message"}

    chat_id = message.get("chat", {}).get("id")
    if TELEGRAM_CHAT_ID and str(chat_id).strip() != TELEGRAM_CHAT_ID:
        log_event(
            db,
            "telegram",
            "message_ignored",
            f"chat_id {chat_id!r} != configured {TELEGRAM_CHAT_ID!r}",
        )
        return {"handled": False, "reason": "unknown chat"}

    text = message.get("text")
    if not text:
        return {"handled": False, "reason": "no text"}

    checkin_date = (
        datetime.fromtimestamp(message["date"], tz=dt_timezone.utc).astimezone(LOCAL_TZ).date()
        if message.get("date")
        else date.today()
    )

    # A pending propose-confirm-write action takes priority over everything
    # else -- this reply is almost certainly answering it.
    pending_proposal = _pending_proposal(db)
    if pending_proposal is not None:
        db.add(TelegramCheckin(date=checkin_date, raw_message=text))
        db.commit()
        log_event(db, "telegram", "checkin_received", text[:200])
        decision = coach_plan_adjust.classify_proposal_reply(text)
        coach_conversation.resolve_proposal(db, pending_proposal, decision, source="telegram", notify_telegram=True)
        return {"handled": True}

    ride_id = _pending_ride_feel_ask(db)
    db.add(TelegramCheckin(date=checkin_date, raw_message=text, ride_id=ride_id))
    db.commit()
    if ride_id is not None:
        log_event(db, "telegram", "ride_feel_answered", f"ride_id={ride_id}")
    log_event(
        db,
        "telegram",
        "checkin_received",
        text[:200] if ride_id is None else f"ride_id={ride_id} | {text[:200]}",
    )

    if ride_id is None:
        # respond_to_generic stays False here -- Telegram carries plenty of
        # non-plan chatter (numeric check-ins, small talk) that should stay
        # silent, unlike the dashboard's dedicated "Adjust with coach" page.
        coach_conversation.handle_athlete_message(db, "telegram", text, notify_telegram=True)

    return {"handled": True}
