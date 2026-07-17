from datetime import date as date_type
from datetime import datetime, timedelta
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
    coach_constraint_drift,
    coach_context,
    coach_conversation,
    coach_missed_workout,
    coach_morning,
    coach_plan_adjust,
    coach_plan_compile,
    coach_ride,
    coach_weekly_summary,
    dashboard,
    health_ingest,
    llm_pricing,
    llm_usage,
    messaging_settings,
    plan_blocks,
    plan_constraints,
    planned_workouts,
    race_goal,
    race_plan,
    readiness,
    strava,
    strava_webhook,
    telegram,
)
from .database import engine, get_db
from .models import PlanAdjustmentProposal, RideSummary


class PlannedWorkoutIn(BaseModel):
    date: date_type
    target_tss: Optional[float] = None
    zone: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None


class MessagingSettingIn(BaseModel):
    enabled: bool


class ConstraintIn(BaseModel):
    text: str


class AskCoachIn(BaseModel):
    message: str


class GoalIn(BaseModel):
    name: Optional[str] = None
    date: Optional[date_type] = None
    distance_km: Optional[float] = None
    elevation_m: Optional[float] = None
    hills: Optional[int] = None


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
def backfill_rides(days: int = 60, db: Session = Depends(get_db)):
    return backfill.run_backfill(db, days)


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


class ModelIn(BaseModel):
    model: str


@app.get("/llm/cost")
def llm_cost(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 90))
    return llm_usage.report(db, days)


@app.put("/llm/model")
def set_llm_model(body: ModelIn, db: Session = Depends(get_db)):
    if not llm_pricing.is_known(body.model):
        raise HTTPException(status_code=400, detail="unknown model")
    llm_usage.set_active_model(db, body.model)
    return {"active_model": body.model}


@app.get("/rides/recent")
def rides_recent(limit: int = 10, db: Session = Depends(get_db)):
    rides = (
        db.query(RideSummary)
        .order_by(RideSummary.start_date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "strava_activity_id": r.strava_activity_id,
            "date": r.start_date.isoformat(),
            "name": r.name,
            "distance_km": round(r.distance_m / 1000, 1) if r.distance_m else None,
        }
        for r in rides
    ]


@app.get("/rides")
def list_rides_range(days: int = 180, db: Session = Depends(get_db)):
    """Recorded rides (Bucket 1) with actual TSS + headline stats, for the
    Plan calendar. Local ride date is derived per row; a 1-day datetime
    buffer keeps timezone conversion from dropping edge rides."""
    days = max(1, min(days, 730))
    cutoff = datetime.now(dashboard.LOCAL_TZ) - timedelta(days=days + 1)
    rows = (
        db.query(RideSummary)
        .filter(RideSummary.start_date >= cutoff)
        .order_by(RideSummary.start_date)
        .all()
    )
    out = []
    for r in rows:
        out.append({
            "strava_activity_id": r.strava_activity_id,
            "date": r.start_date.astimezone(dashboard.LOCAL_TZ).date().isoformat(),
            "name": r.name,
            "tss": round(r.ride_tss, 1) if r.ride_tss is not None else None,
            "distance_km": round(r.distance_m / 1000, 1) if r.distance_m else None,
            "moving_minutes": round(r.moving_time_s / 60) if r.moving_time_s else None,
            "elevation_gain_m": r.elevation_gain_m,
            "average_watts": r.average_watts,
            "weighted_avg_watts": r.weighted_avg_watts,
            "average_heartrate": r.average_heartrate,
            "max_heartrate": r.max_heartrate,
        })
    return out


@app.get("/planned-workouts")
def list_planned_workouts(db: Session = Depends(get_db)):
    return planned_workouts.list_workouts(db)


@app.post("/planned-workouts")
def create_planned_workout(workout: PlannedWorkoutIn, db: Session = Depends(get_db)):
    return planned_workouts.create_workout(
        db, workout.date, workout.target_tss, workout.zone, workout.notes, workout.title
    )


@app.put("/planned-workouts/{workout_id}")
def update_planned_workout(
    workout_id: int, workout: PlannedWorkoutIn, db: Session = Depends(get_db)
):
    result = planned_workouts.update_workout(
        db, workout_id, workout.date, workout.target_tss, workout.zone, workout.notes, workout.title
    )
    if result is None:
        raise HTTPException(status_code=404, detail="not found")
    return result


@app.delete("/planned-workouts/{workout_id}")
def delete_planned_workout(workout_id: int, db: Session = Depends(get_db)):
    return planned_workouts.delete_workout(db, workout_id)


@app.post("/planned-workouts/backfill-titles")
def backfill_workout_titles(db: Session = Depends(get_db)):
    """One-off: give short titles to workouts created before the title/notes
    split (detail in notes, no title). Idempotent -- safe to call more than
    once; only fills rows still missing a title."""
    return coach_plan_compile.backfill_titles(db)


@app.get("/planned-workouts/projection")
def planned_workouts_projection(days: int = 14, db: Session = Depends(get_db)):
    # Horizon is selectable from the dashboard's Projection range control;
    # clamp to a sane ceiling. Default stays 14 for any other caller.
    days = max(1, min(days, 400))
    return readiness.project_forward(db, horizon_days=days)


@app.get("/plan/overview")
def plan_overview(db: Session = Depends(get_db)):
    return race_plan.get_overview(db)


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


@app.get("/telegram/test-ride-debrief/{strava_activity_id}")
def telegram_test_ride_debrief(strava_activity_id: int, db: Session = Depends(get_db)):
    ride = (
        db.query(RideSummary)
        .filter(RideSummary.strava_activity_id == strava_activity_id)
        .first()
    )
    if ride is None:
        raise HTTPException(status_code=404, detail="ride not found")
    return telegram.send_post_ride_debrief(db, ride)


@app.get("/coach/context")
def coach_context_endpoint(db: Session = Depends(get_db)):
    return coach_context.get_coach_context(db)


@app.get("/coach/test-ping")
def coach_test_ping():
    text = ai_coach.ask_claude("Reply with exactly one short sentence confirming you received this.", category="ping")
    return {"configured": bool(ai_coach.ANTHROPIC_API_KEY), "response": text}


@app.get("/coach/morning-context")
def coach_morning_context(db: Session = Depends(get_db)):
    return coach_morning.build_morning_context(db)


@app.get("/coach/verdict-preview")
def coach_verdict_preview(db: Session = Depends(get_db)):
    return coach_morning.explain_verdict(db)


@app.get("/messaging/settings")
def messaging_settings_list(db: Session = Depends(get_db)):
    return messaging_settings.list_settings(db)


@app.post("/messaging/settings/{key}")
def messaging_settings_update(
    key: str, setting: MessagingSettingIn, db: Session = Depends(get_db)
):
    return messaging_settings.set_enabled(db, key, setting.enabled)


@app.get("/coach/ride-preview/{strava_activity_id}")
def coach_ride_preview(strava_activity_id: int, db: Session = Depends(get_db)):
    ride = (
        db.query(RideSummary)
        .filter(RideSummary.strava_activity_id == strava_activity_id)
        .first()
    )
    if ride is None:
        raise HTTPException(status_code=404, detail="ride not found")
    return {
        "context": coach_ride.build_ride_context(db, ride),
        "explanation": coach_ride.explain_ride(db, ride),
    }


@app.get("/coach/missed-workout-preview")
def coach_missed_workout_preview(
    check_date: Optional[date_type] = None, db: Session = Depends(get_db)
):
    checked = check_date or (datetime.now(telegram.LOCAL_TZ).date() - timedelta(days=1))
    context = coach_missed_workout.build_missed_workout_context(db, checked)
    if context is None:
        return {"date": checked.isoformat(), "context": None, "explanation": None}
    return {
        "context": context,
        "explanation": coach_missed_workout.explain_missed_workout(db, context),
    }


@app.get("/coach/weekly-summary-preview")
def coach_weekly_summary_preview(week: Optional[int] = None, db: Session = Depends(get_db)):
    if week is not None:
        target_week = plan_blocks.get_block(db, week)
    else:
        today_local = datetime.now(telegram.LOCAL_TZ).date()
        target_week = coach_weekly_summary.find_week_ending_yesterday(db, today_local)
    if target_week is None:
        return {"week": None, "context": None, "explanation": None}
    context = coach_weekly_summary.build_weekly_context(db, target_week)
    return {
        "context": context,
        "explanation": coach_weekly_summary.explain_week(db, context),
    }


@app.get("/brief/constraints")
def list_constraints(db: Session = Depends(get_db)):
    return plan_constraints.list_constraints(db, active_only=False)


@app.post("/brief/constraints")
def add_constraint(constraint: ConstraintIn, db: Session = Depends(get_db)):
    return plan_constraints.add_constraint(db, constraint.text)


@app.delete("/brief/constraints/{constraint_id}")
def deactivate_constraint(constraint_id: int, db: Session = Depends(get_db)):
    return plan_constraints.deactivate_constraint(db, constraint_id)


@app.get("/coach/drift-preview")
def coach_drift_preview(db: Session = Depends(get_db)):
    context = coach_constraint_drift.build_drift_context(db)
    if context is None:
        return {"context": None, "explanation": None}
    return {
        "context": context,
        "explanation": coach_constraint_drift.explain_drift(db, context),
    }


@app.get("/coach/disruption-preview")
def coach_disruption_preview(message: str, db: Session = Depends(get_db)):
    proposal = coach_plan_adjust.propose_adjustment(db, message)
    if proposal is None:
        return {"proposal": None, "reason": "no active plan week or coach unavailable"}
    return {"proposal": proposal}


@app.get("/telegram/test-disruption")
def telegram_test_disruption(message: str, db: Session = Depends(get_db)):
    coach_conversation.handle_athlete_message(db, "telegram", message, notify_telegram=True)
    return {"triggered": True}


@app.get("/brief/goal")
def get_goal(db: Session = Depends(get_db)):
    return race_goal.get_goal(db)


@app.put("/brief/goal")
def update_goal(body: GoalIn, db: Session = Depends(get_db)):
    return race_goal.update_goal(
        db, name=body.name, date=body.date, distance_km=body.distance_km,
        elevation_m=body.elevation_m, hills=body.hills,
    )


@app.get("/coach/thread")
def coach_thread(limit: int = 50, db: Session = Depends(get_db)):
    return coach_conversation.get_thread(db, limit=limit)


@app.post("/coach/ask")
def coach_ask(body: AskCoachIn, db: Session = Depends(get_db)):
    # Dashboard entry point for the unified plan conversation (stories 6+7)
    # -- same coach brain as Telegram, and a genuine mirror: whatever gets
    # said here also lands on Telegram, so the conversation is really one
    # thread regardless of which surface you're on. Every message sent here
    # is presumed plan-related, so a generic classification still gets a
    # clarifying reply instead of silently doing nothing.
    return coach_conversation.handle_athlete_message(db, "dashboard", body.message, notify_telegram=True, respond_to_generic=True)


@app.post("/plan/proposals/{proposal_id}/confirm")
def plan_proposal_confirm(proposal_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(PlanAdjustmentProposal)
        .filter(PlanAdjustmentProposal.id == proposal_id, PlanAdjustmentProposal.status == "pending")
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no pending proposal with that id")
    activity_log.log_event(db, "dashboard", "checkin_received", "Confirmed ✓")
    coach_conversation.echo_athlete_action("dashboard", True, "Confirmed ✓")
    return coach_conversation.resolve_proposal(db, row, "confirm", source="dashboard", notify_telegram=True)


@app.post("/plan/proposals/{proposal_id}/reject")
def plan_proposal_reject(proposal_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(PlanAdjustmentProposal)
        .filter(PlanAdjustmentProposal.id == proposal_id, PlanAdjustmentProposal.status == "pending")
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no pending proposal with that id")
    activity_log.log_event(db, "dashboard", "checkin_received", "Rejected ✕")
    coach_conversation.echo_athlete_action("dashboard", True, "Rejected ✕")
    return coach_conversation.resolve_proposal(db, row, "reject", source="dashboard", notify_telegram=True)
