from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import backfill, dashboard, health_ingest, readiness, strava
from .database import engine, get_db

STATIC_DIR = Path(__file__).parent / "static"

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


@app.get("/backfill/rides")
def backfill_rides(db: Session = Depends(get_db)):
    return backfill.run_backfill(db)


@app.get("/readiness/recompute")
def readiness_recompute(db: Session = Depends(get_db)):
    return readiness.recompute(db)


@app.post("/health/ingest")
async def ingest_health_data(
    request: Request, token: str = "", db: Session = Depends(get_db)
):
    if not health_ingest.HAE_INGEST_TOKEN or token != health_ingest.HAE_INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    payload = await request.json()
    return health_ingest.ingest_payload(db, payload)


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/dashboard/data")
def dashboard_data(db: Session = Depends(get_db)):
    return dashboard.get_dashboard_data(db)
