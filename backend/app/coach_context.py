from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import race_goal
from .models import DailyReadiness, HealthSample, PlannedWorkout, RideSummary, TelegramCheckin

# Personal single-user app; matches the local timezone used elsewhere
# (dashboard.py, telegram.py) for bucketing events into calendar days.
from .localtime import LOCAL_TZ

READINESS_TREND_DAYS = 14
RECENT_RIDES = 5
RECENT_HEALTH_NIGHTS = 7
RECENT_CHECKINS = 5
UPCOMING_WORKOUT_DAYS = 7


def _local_date(ts: datetime) -> date:
    return ts.astimezone(LOCAL_TZ).date()


def _goal(db: Session) -> dict:
    goal = race_goal.get_goal(db)
    event_date = datetime.strptime(goal["date"], "%Y-%m-%d").date()
    return {**goal, "days_remaining": (event_date - date.today()).days}


def _readiness(db: Session) -> dict:
    cutoff = date.today() - timedelta(days=READINESS_TREND_DAYS)
    rows = (
        db.query(DailyReadiness)
        .filter(DailyReadiness.date >= cutoff)
        .order_by(DailyReadiness.date)
        .all()
    )
    trend = [
        {"date": row.date.isoformat(), "ctl": row.ctl, "atl": row.atl, "tsb": row.tsb}
        for row in rows
    ]
    latest = trend[-1] if trend else None
    latest_verdict = rows[-1].verdict if rows else None
    return {"latest": {**latest, "verdict": latest_verdict} if latest else None, "trend": trend}


def _recent_rides(db: Session) -> list:
    rows = (
        db.query(RideSummary)
        .order_by(RideSummary.start_date.desc())
        .limit(RECENT_RIDES)
        .all()
    )
    return [
        {
            "date": row.start_date.date().isoformat(),
            "name": row.name,
            "distance_km": round(row.distance_m / 1000, 1) if row.distance_m else None,
            "tss": round(row.ride_tss, 1) if row.ride_tss else None,
        }
        for row in reversed(rows)
    ]


def _recent_health(db: Session) -> dict:
    nights = (
        db.query(HealthSample)
        .filter(HealthSample.metric_name == "sleep_analysis")
        .order_by(HealthSample.timestamp.desc())
        .limit(RECENT_HEALTH_NIGHTS)
        .all()
    )
    nights = list(reversed(nights))

    sleep = []
    hrv = []
    resting_hr = []

    for night in nights:
        payload = night.raw_payload or {}
        sleep_start = night.timestamp
        night_date = _local_date(sleep_start)
        sleep.append({"date": night_date.isoformat(), "total_hours": payload.get("totalSleep")})

        sleep_end_raw = payload.get("sleepEnd")
        if sleep_end_raw:
            sleep_end = datetime.strptime(sleep_end_raw, "%Y-%m-%d %H:%M:%S %z")
            hrv_samples = (
                db.query(HealthSample)
                .filter(
                    HealthSample.metric_name == "heart_rate_variability",
                    HealthSample.timestamp >= sleep_start,
                    HealthSample.timestamp <= sleep_end,
                )
                .all()
            )
            values = [s.value for s in hrv_samples if s.value is not None]
            if values:
                hrv.append({"date": night_date.isoformat(), "value": round(sum(values) / len(values), 1)})

    rhr_rows = db.query(HealthSample).filter(HealthSample.metric_name == "resting_heart_rate").all()
    recent_dates = {n["date"] for n in sleep}
    for row in rhr_rows:
        row_date = _local_date(row.timestamp).isoformat()
        if row_date in recent_dates:
            resting_hr.append({"date": row_date, "value": row.value})

    return {"sleep": sleep, "hrv": hrv, "resting_hr": resting_hr}


def _recent_checkins(db: Session) -> list:
    rows = (
        db.query(TelegramCheckin)
        .order_by(TelegramCheckin.created_at.desc())
        .limit(RECENT_CHECKINS)
        .all()
    )
    return [
        {"date": row.date.isoformat(), "message": row.raw_message}
        for row in reversed(rows)
    ]


def _upcoming_workouts(db: Session) -> list:
    today = date.today()
    cutoff = today + timedelta(days=UPCOMING_WORKOUT_DAYS)
    rows = (
        db.query(PlannedWorkout)
        .filter(PlannedWorkout.date >= today, PlannedWorkout.date <= cutoff)
        .order_by(PlannedWorkout.date)
        .all()
    )
    return [
        {
            "date": row.date.isoformat(),
            "target_tss": row.target_tss,
            "zone": row.zone,
            "notes": row.notes,
        }
        for row in rows
    ]


def get_coach_context(db: Session) -> dict:
    return {
        "goal": _goal(db),
        "readiness": _readiness(db),
        "recent_rides": _recent_rides(db),
        "recent_health": _recent_health(db),
        "recent_checkins": _recent_checkins(db),
        "upcoming_workouts": _upcoming_workouts(db),
    }
