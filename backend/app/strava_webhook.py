import os

import httpx

from . import backfill, readiness, telegram
from .activity_log import log_event
from .database import SessionLocal
from .models import RideSummary
from .strava import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

STRAVA_WEBHOOK_VERIFY_TOKEN = os.environ.get("STRAVA_WEBHOOK_VERIFY_TOKEN", "")
PUSH_SUBSCRIPTION_URL = "https://www.strava.com/api/v3/push_subscriptions"


def create_subscription(callback_url: str) -> dict:
    response = httpx.post(
        PUSH_SUBSCRIPTION_URL,
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "callback_url": callback_url,
            "verify_token": STRAVA_WEBHOOK_VERIFY_TOKEN,
        },
        timeout=15,
    )
    return {"status_code": response.status_code, "body": response.json()}


def get_subscription() -> dict:
    response = httpx.get(
        PUSH_SUBSCRIPTION_URL,
        params={"client_id": STRAVA_CLIENT_ID, "client_secret": STRAVA_CLIENT_SECRET},
        timeout=15,
    )
    return {"status_code": response.status_code, "body": response.json()}


def process_event(event: dict) -> None:
    object_type = event.get("object_type")
    aspect_type = event.get("aspect_type")
    object_id = event.get("object_id")

    db = SessionLocal()
    try:
        if object_type != "activity" or object_id is None:
            log_event(db, "strava_webhook", "event_ignored", f"{event}")
            return
        # aspect_type == "update" is intentionally ignored for now -- only
        # new rides landing and rides being removed are handled.
        if aspect_type not in ("create", "delete"):
            log_event(
                db,
                "strava_webhook",
                "event_ignored",
                f"activity {object_id} aspect_type={aspect_type}",
            )
            return

        new_ride_id = None
        if aspect_type == "create":
            result = backfill.ingest_single_activity(db, object_id)
            new_ride_id = result.get("ride_id")
        elif aspect_type == "delete":
            backfill.delete_activity(db, object_id)
        readiness.recompute(db)

        if new_ride_id is not None:
            # Recompute above fills in ride_tss -- fetch after, so the
            # debrief sees it rather than a null.
            ride = db.query(RideSummary).filter(RideSummary.id == new_ride_id).first()
            if ride is not None:
                telegram.send_post_ride_debrief(db, ride)
    finally:
        db.close()
