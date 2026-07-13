import os
from datetime import datetime

from sqlalchemy.orm import Session

from . import readiness, telegram
from .activity_log import log_event
from .models import HealthSample

HAE_INGEST_TOKEN = os.environ.get("HAE_INGEST_TOKEN", "")


def _parse_date(value: str) -> datetime:
    # HAE dates look like "2026-07-09 00:36:06 +0900"
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")


def _sample_exists(db: Session, metric_name: str, timestamp: datetime) -> bool:
    return (
        db.query(HealthSample)
        .filter(
            HealthSample.metric_name == metric_name,
            HealthSample.timestamp == timestamp,
        )
        .first()
        is not None
    )


def _ingest_scalar_metric(db: Session, metric_name: str, samples: list) -> int:
    saved = 0
    for sample in samples:
        timestamp = _parse_date(sample["date"])
        if _sample_exists(db, metric_name, timestamp):
            continue
        db.add(
            HealthSample(
                metric_name=metric_name,
                timestamp=timestamp,
                value=sample.get("qty"),
                source=sample.get("source"),
                raw_payload=sample,
            )
        )
        saved += 1
    return saved


def _ingest_sleep_metric(db: Session, samples: list) -> int:
    # Sleep has no `qty` -- it's a session record. Dedup on sleepStart,
    # not `date`, since `date` is just the midnight-anchored day marker.
    saved = 0
    for sample in samples:
        timestamp = _parse_date(sample["sleepStart"])
        if _sample_exists(db, "sleep_analysis", timestamp):
            continue
        db.add(
            HealthSample(
                metric_name="sleep_analysis",
                timestamp=timestamp,
                value=sample.get("totalSleep"),
                source=sample.get("source"),
                raw_payload=sample,
            )
        )
        saved += 1
    return saved


def ingest_payload(db: Session, payload: dict) -> dict:
    metrics = payload.get("data", {}).get("metrics", [])

    saved = 0
    skipped = 0
    by_metric = {}

    for metric in metrics:
        name = metric.get("name")
        samples = metric.get("data", [])
        if name == "sleep_analysis":
            count = _ingest_sleep_metric(db, samples)
        else:
            count = _ingest_scalar_metric(db, name, samples)
        by_metric[name] = count
        saved += count
        skipped += len(samples) - count

    db.commit()
    log_event(
        db,
        "health_ingest",
        "payload_received",
        f"saved {saved}, skipped {skipped}, by_metric {by_metric}",
    )

    # health-data-arrived trigger, per the locked architecture: roll
    # CTL/ATL/TSB and push the morning verdict (deduped to once/day), plus
    # the two other checks that ride along the same daily trigger --
    # missed-workout and weekly-summary each dedupe on their own key so
    # re-arriving health data the same day is a no-op.
    readiness.recompute(db)
    telegram.send_morning_verdict(db)
    telegram.send_missed_workout_nudge(db)
    telegram.send_weekly_summary(db)

    return {"saved": saved, "skipped_existing": skipped, "by_metric": by_metric}
