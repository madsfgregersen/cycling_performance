import os
import time

import httpx
from sqlalchemy.orm import Session

from .models import StravaToken

STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID", "264132")
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPE = "activity:read_all,profile:read_all"


def build_authorize_url(redirect_uri: str) -> str:
    params = {
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
    }
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def _save_token(db: Session, payload: dict) -> StravaToken:
    token = db.query(StravaToken).first()
    if token is None:
        token = StravaToken()
        db.add(token)
    token.access_token = payload["access_token"]
    token.refresh_token = payload["refresh_token"]
    token.expires_at = payload["expires_at"]
    db.commit()
    db.refresh(token)
    return token


def exchange_code(db: Session, code: str) -> StravaToken:
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    response.raise_for_status()
    return _save_token(db, response.json())


def get_valid_access_token(db: Session) -> str:
    token = db.query(StravaToken).first()
    if token is None:
        raise RuntimeError("No Strava token stored yet — visit /strava/authorize first.")

    if token.expires_at <= int(time.time()) + 60:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "refresh_token": token.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10,
        )
        response.raise_for_status()
        token = _save_token(db, response.json())

    return token.access_token


def get_activity(db: Session, activity_id: int) -> dict:
    access_token = get_valid_access_token(db)
    response = httpx.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_athlete_profile(db: Session) -> dict:
    access_token = get_valid_access_token(db)
    response = httpx.get(
        "https://www.strava.com/api/v3/athlete",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
