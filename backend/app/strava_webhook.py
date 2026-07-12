import os

import httpx

from . import backfill, readiness
from .database import SessionLocal
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

    if object_type != "activity" or object_id is None:
        return
    # aspect_type == "update" is intentionally ignored for now -- only
    # new rides landing and rides being removed are handled.
    if aspect_type not in ("create", "delete"):
        return

    db = SessionLocal()
    try:
        if aspect_type == "create":
            backfill.ingest_single_activity(db, object_id)
        elif aspect_type == "delete":
            backfill.delete_activity(db, object_id)
        readiness.recompute(db)
    finally:
        db.close()
