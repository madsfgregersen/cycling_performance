import json
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import readiness, recovery_signals
from .models import DailyReadiness, HealthSample, IntegrationLog

# Personal single-user app; all recorded samples are in this timezone.
from .localtime import LOCAL_TZ

# Widest history the Training-load chart's range selector can show (360d
# back). The client slices this down to the chosen range.
LOAD_HISTORY_DAYS = 360
# Widest forward projection the range selector can show (180d ahead).
LOAD_PROJECTION_DAYS = 180
RECOVERY_HISTORY_NIGHTS = 60
# Sleep stays a tighter window -- 60 stacked bars would be unreadable.
SLEEP_HISTORY_NIGHTS = 14


def _local_date(ts: datetime) -> date:
    return ts.astimezone(LOCAL_TZ).date()


def _load_history(db: Session) -> list:
    cutoff = date.today() - timedelta(days=LOAD_HISTORY_DAYS)
    rows = (
        db.query(DailyReadiness)
        .filter(DailyReadiness.date >= cutoff)
        .order_by(DailyReadiness.date)
        .all()
    )
    return [
        {
            "date": row.date.isoformat(),
            "ctl": row.ctl,
            "atl": row.atl,
            "tsb": row.tsb,
            "verdict": row.verdict,
        }
        for row in rows
    ]


def _overnight_avg(db: Session, metric_name: str, sleep_start: datetime, sleep_end: datetime):
    samples = (
        db.query(HealthSample)
        .filter(
            HealthSample.metric_name == metric_name,
            HealthSample.timestamp >= sleep_start,
            HealthSample.timestamp <= sleep_end,
        )
        .all()
    )
    values = [sample.value for sample in samples if sample.value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _resting_hr_for_date(db: Session, night_date: date):
    # Resting HR arrives ~once/day and can lag behind the rest, so match by
    # local calendar date rather than an exact overnight window.
    rows = db.query(HealthSample).filter(HealthSample.metric_name == "resting_heart_rate").all()
    for row in rows:
        if _local_date(row.timestamp) == night_date:
            return row.value
    return None


def _recovery_tiles(db: Session) -> dict:
    nights = recovery_signals.canonical_nights(db, RECOVERY_HISTORY_NIGHTS)

    hrv = []
    resting_hr = []
    sleep = []

    for night in nights:
        sleep_start = night["start"]
        sleep_end = night["end"]
        night_date = _local_date(sleep_start)

        hrv_avg = (
            _overnight_avg(db, "heart_rate_variability", sleep_start, sleep_end)
            if sleep_end
            else None
        )
        hrv.append({"date": night_date.isoformat(), "value": hrv_avg})
        resting_hr.append(
            {"date": night_date.isoformat(), "value": _resting_hr_for_date(db, night_date)}
        )
        sleep.append(
            {
                "date": night_date.isoformat(),
                "total": night["total"],
                "deep": night["deep"],
                "core": night["core"],
                "rem": night["rem"],
            }
        )

    # HRV + resting HR run the full 60-night window; sleep stays at the
    # last 14 nights so its stacked bars remain legible.
    return {"hrv": hrv, "resting_hr": resting_hr, "sleep": sleep[-SLEEP_HISTORY_NIGHTS:]}


def _latest_morning_brief(db: Session):
    """The most recent coach morning brief, cached when the morning verdict
    was sent (see telegram.send_morning_verdict). Returns None if none has
    been generated yet -- the Now page then simply hides the coach block."""
    row = (
        db.query(IntegrationLog)
        .filter(IntegrationLog.source == "coach", IntegrationLog.event == "morning_brief")
        .order_by(IntegrationLog.created_at.desc())
        .first()
    )
    if row is None or not row.summary:
        return None
    try:
        brief = json.loads(row.summary)
    except (ValueError, TypeError):
        return None
    return {
        "date": brief.get("date"),
        "headline": brief.get("headline", ""),
        "why": brief.get("why", ""),
    }


def get_dashboard_data(db: Session) -> dict:
    load_history = _load_history(db)
    latest = load_history[-1] if load_history else None

    return {
        "latest": latest,
        "load_history": load_history,
        "load_projection": readiness.project_forward(db, horizon_days=LOAD_PROJECTION_DAYS),
        "recovery": _recovery_tiles(db),
        "morning_brief": _latest_morning_brief(db),
    }
