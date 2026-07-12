from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import strava
from .database import engine, get_db

app = FastAPI(title="Cycling Performance API")


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/strava/authorize")
def strava_authorize(request: Request):
    redirect_uri = str(request.base_url) + "strava/callback"
    return RedirectResponse(strava.build_authorize_url(redirect_uri))


@app.get("/strava/callback")
def strava_callback(code: str, db: Session = Depends(get_db)):
    strava.exchange_code(db, code)
    return {"status": "connected"}


@app.get("/strava/status")
def strava_status(db: Session = Depends(get_db)):
    athlete = strava.get_athlete_profile(db)
    return {"connected_as": f"{athlete.get('firstname')} {athlete.get('lastname')}"}
