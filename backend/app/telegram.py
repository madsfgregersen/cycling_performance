import os
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

import httpx
from sqlalchemy.orm import Session

from .activity_log import log_event
from .models import DailyReadiness, IntegrationLog, TelegramCheckin

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

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
    if _already_sent_today(db):
        return {"sent": False, "reason": "already sent today"}

    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()
    if latest is None:
        log_event(db, "telegram", "verdict_skipped", "no readiness data yet")
        return {"sent": False, "reason": "no data"}

    text = (
        f"{_verdict_emoji(latest.verdict)} Morning readiness: "
        f"{(latest.verdict or 'unknown').capitalize()}\n"
        f"TSB {latest.tsb:+.1f} · CTL {latest.ctl:.1f} · ATL {latest.atl:.1f}\n"
        f"As of {latest.date.isoformat()}"
    )
    sent = send_message(text)
    log_event(
        db, "telegram", "verdict_sent" if sent else "verdict_send_failed", text.replace("\n", " | ")
    )
    return {"sent": sent}


def process_update(db: Session, update: dict) -> dict:
    message = update.get("message") or update.get("edited_message")
    if message is None:
        return {"handled": False, "reason": "no message"}

    chat_id = message.get("chat", {}).get("id")
    if TELEGRAM_CHAT_ID and str(chat_id) != str(TELEGRAM_CHAT_ID):
        log_event(db, "telegram", "message_ignored", f"unknown chat_id {chat_id}")
        return {"handled": False, "reason": "unknown chat"}

    text = message.get("text")
    if not text:
        return {"handled": False, "reason": "no text"}

    checkin_date = (
        datetime.fromtimestamp(message["date"], tz=dt_timezone.utc).astimezone(LOCAL_TZ).date()
        if message.get("date")
        else date.today()
    )
    db.add(TelegramCheckin(date=checkin_date, raw_message=text))
    db.commit()
    log_event(db, "telegram", "checkin_received", text[:200])
    return {"handled": True}
