from datetime import date as date_type
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import (
    activity_log,
    ai_coach,
    backfill,
    coach_context,
    dashboard,
    health_ingest,
    planned_workouts,
    race_plan,
    readiness,
    strava,
    strava_webhook,
    telegram,
)
from .database import engine, get_db


class PlannedWorkoutIn(BaseModel):
    date: date_type
    target_tss: Optional[float] = None
    zone: Optional[str] = None
    notes: Optional[str] = None


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Cycling Performance API")


def public_base_url(request: Request) -> str:
    # Railway terminates TLS at the edge and forwards plain HTTP internally,
    # so request.base_url reports "http://" even though the public URL is
    # always "https://". Force it, since some callers (e.g. Strava's
    # webhook validator) don't follow redirects.
    base = str(request.base_url)
    if base.startswith("http://"):
        base = "https://" + base[len("http://") :]
    return base


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/strava/authorize")
def strava_authorize(request: Request):
    redirect_uri = public_base_url(request) + "strava/callback"
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


@app.get("/strava/webhook")
def strava_webhook_verify(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    if (
        not strava_webhook.STRAVA_WEBHOOK_VERIFY_TOKEN
        or hub_verify_token != strava_webhook.STRAVA_WEBHOOK_VERIFY_TOKEN
    ):
        raise HTTPException(status_code=403, detail="invalid verify token")
    return {"hub.challenge": hub_challenge}


@app.post("/strava/webhook")
async def strava_webhook_receive(request: Request, background_tasks: BackgroundTasks):
    event = await request.json()
    background_tasks.add_task(strava_webhook.process_event, event)
    return {"status": "received"}


@app.get("/strava/webhook/subscribe")
def strava_webhook_subscribe(request: Request):
    callback_url = public_base_url(request) + "strava/webhook"
    return strava_webhook.create_subscription(callback_url)


@app.get("/strava/webhook/status")
def strava_webhook_status():
    return strava_webhook.get_subscription()


@app.get("/logs")
def logs(db: Session = Depends(get_db)):
    return activity_log.recent_events(db)


@app.get("/planned-workouts")
def list_planned_workouts(db: Session = Depends(get_db)):
    return planned_workouts.list_workouts(db)


@app.post("/planned-workouts")
def create_planned_workout(workout: PlannedWorkoutIn, db: Session = Depends(get_db)):
    return planned_workouts.create_workout(
        db, workout.date, workout.target_tss, workout.zone, workout.notes
    )


@app.put("/planned-workouts/{workout_id}")
def update_planned_workout(
    workout_id: int, workout: PlannedWorkoutIn, db: Session = Depends(get_db)
):
    result = planned_workouts.update_workout(
        db, workout_id, workout.date, workout.target_tss, workout.zone, workout.notes
    )
    if result is None:
        raise HTTPException(status_code=404, detail="not found")
    return result


@app.delete("/planned-workouts/{workout_id}")
def delete_planned_workout(workout_id: int, db: Session = Depends(get_db)):
    return planned_workouts.delete_workout(db, workout_id)


@app.get("/planned-workouts/projection")
def planned_workouts_projection(db: Session = Depends(get_db)):
    return readiness.project_forward(db)


@app.get("/plan/overview")
def plan_overview():
    return race_plan.get_overview()


@app.post("/telegram/webhook")
async def telegram_webhook_receive(request: Request, db: Session = Depends(get_db)):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not telegram.TELEGRAM_WEBHOOK_SECRET or secret != telegram.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid secret token")
    update = await request.json()
    return telegram.process_update(db, update)


@app.get("/telegram/webhook/subscribe")
def telegram_webhook_subscribe(request: Request):
    callback_url = public_base_url(request) + "telegram/webhook"
    return telegram.set_webhook(callback_url)


@app.get("/telegram/webhook/status")
def telegram_webhook_status():
    return telegram.get_webhook_info()


@app.get("/telegram/test")
def telegram_test(db: Session = Depends(get_db)):
    return telegram.send_morning_verdict(db)


@app.get("/coach/context")
def coach_context_endpoint(db: Session = Depends(get_db)):
    return coach_context.get_coach_context(db)


@app.get("/coach/test-ping")
def coach_test_ping():
    text = ai_coach.ask_claude("Reply with exactly one short sentence confirming you received this.")
    return {"configured": bool(ai_coach.ANTHROPIC_API_KEY), "response": text}
