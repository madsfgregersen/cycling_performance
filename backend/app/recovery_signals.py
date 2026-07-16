from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from .models import HealthSample

# Personal single-user app; matches the local timezone used elsewhere.
LOCAL_TZ = dt_timezone(timedelta(hours=9))

BASELINE_NIGHTS = 30

# Metrics averaged over the overnight sleep window (need sleepStart/sleepEnd).
OVERNIGHT_METRICS = ["heart_rate_variability", "apple_sleeping_wrist_temperature", "respiratory_rate"]


def _local_date(ts: datetime) -> date:
    return ts.astimezone(LOCAL_TZ).date()


def canonical_nights(db: Session, max_nights: int) -> list:
    """One sleep_analysis record per night, most recent `max_nights` nights,
    oldest first.

    HAE emits many overlapping records for a single night -- cumulative
    snapshots with progressively later sleepStarts, plus a second source
    (e.g. AutoSleep). Storing each as its own row made downstream code treat
    every snapshot as a separate 'night', so it read a late fragment (~1.5h)
    instead of the complete session (~6.8h) and counted rows, not nights, for
    the baseline. Collapse by night (the payload's midnight-anchored `date`)
    and keep the record with the largest totalSleep -- the full session."""
    rows = (
        db.query(HealthSample)
        .filter(HealthSample.metric_name == "sleep_analysis")
        .all()
    )
    best_by_night = {}
    for row in rows:
        payload = row.raw_payload or {}
        key = payload.get("date") or _local_date(row.timestamp).isoformat()
        total = payload.get("totalSleep") or 0
        best = best_by_night.get(key)
        best_total = (best.raw_payload or {}).get("totalSleep") or 0 if best is not None else -1
        if total > best_total:
            best_by_night[key] = row

    ordered = sorted(best_by_night.values(), key=lambda r: r.timestamp)
    return ordered[-max_nights:]


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
    values = [s.value for s in samples if s.value is not None]
    return sum(values) / len(values) if values else None


def _resting_hr_for_date(db: Session, night_date: date):
    rows = db.query(HealthSample).filter(HealthSample.metric_name == "resting_heart_rate").all()
    for row in rows:
        if _local_date(row.timestamp) == night_date:
            return row.value
    return None


def _per_night_values(db: Session, nights: list) -> dict:
    """For each night (a sleep_analysis HealthSample row), compute this
    night's value for every tracked metric. Returns {metric: [values...]}
    aligned index-for-index with `nights` (None where data is missing)."""
    per_metric = {m: [] for m in OVERNIGHT_METRICS + ["sleep_duration", "resting_heart_rate"]}

    for night in nights:
        payload = night.raw_payload or {}
        sleep_start = night.timestamp
        sleep_end_raw = payload.get("sleepEnd")
        sleep_end = (
            datetime.strptime(sleep_end_raw, "%Y-%m-%d %H:%M:%S %z") if sleep_end_raw else None
        )
        night_date = _local_date(sleep_start)

        per_metric["sleep_duration"].append(payload.get("totalSleep"))
        per_metric["resting_heart_rate"].append(_resting_hr_for_date(db, night_date))

        for metric in OVERNIGHT_METRICS:
            per_metric[metric].append(
                _overnight_avg(db, metric, sleep_start, sleep_end) if sleep_end else None
            )

    return per_metric


def get_recovery_deviations(db: Session) -> list:
    """Today's overnight recovery signals as deviations from a trailing
    baseline average. Omits any metric where there's no baseline or no
    today's value yet -- never fabricate a deviation."""
    nights = canonical_nights(db, BASELINE_NIGHTS + 1)
    if len(nights) < 2:
        return []

    per_metric = _per_night_values(db, nights)

    labels = {
        "heart_rate_variability": "HRV",
        "apple_sleeping_wrist_temperature": "wrist temperature",
        "respiratory_rate": "respiratory rate",
        "sleep_duration": "sleep duration",
        "resting_heart_rate": "resting heart rate",
    }

    deviations = []
    for metric, values in per_metric.items():
        today_value = values[-1]
        baseline_values = [v for v in values[:-1] if v is not None]
        if today_value is None or not baseline_values:
            continue
        baseline = sum(baseline_values) / len(baseline_values)
        deviations.append(
            {
                "metric": labels[metric],
                "today": round(today_value, 2),
                "baseline": round(baseline, 2),
                "baseline_nights": len(baseline_values),
                "deviation_pct": round((today_value - baseline) / baseline * 100, 1)
                if baseline
                else None,
            }
        )

    return deviations
