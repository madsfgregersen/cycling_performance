from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from .models import HealthSample

# Personal single-user app; matches the local timezone used elsewhere.
from .localtime import LOCAL_TZ

BASELINE_NIGHTS = 30

# Metrics averaged over the overnight sleep window (need sleepStart/sleepEnd).
OVERNIGHT_METRICS = ["heart_rate_variability", "apple_sleeping_wrist_temperature", "respiratory_rate"]


def _local_date(ts: datetime) -> date:
    return ts.astimezone(LOCAL_TZ).date()


def _parse_dt(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    except (TypeError, ValueError):
        return None


def _merged_hours(intervals: list) -> float:
    """Total hours covered by a set of (start, end) datetime intervals, with
    overlaps counted once (interval union)."""
    ivs = sorted((s, e) for s, e in intervals if s and e and e > s)
    if not ivs:
        return 0.0
    total = 0.0
    cur_s, cur_e = ivs[0]
    for s, e in ivs[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
    total += (cur_e - cur_s).total_seconds()
    return total / 3600.0


def canonical_nights(db: Session, max_nights: int) -> list:
    """One merged record per night, most recent `max_nights` nights, oldest
    first. Each is a dict: {start, end, total (hours asleep), deep, core, rem}.

    HAE emits many overlapping records per night: cumulative snapshots of one
    session AND separate trackers (Apple Watch, AutoSleep) that each cover a
    different part of the night (e.g. AutoSleep 22:37-00:47, Apple Watch
    00:16-05:51). Picking the single largest record dropped whichever part the
    other tracker covered (Apple: 7:03; largest single: 5:25). Instead:
    - group by night (the payload's wake-date, `date[:10]`, which is stable
      across midnight and across the +09:00->CET tz change);
    - `total` = interval-union of every window in the night (time in bed),
      minus the awake time the fullest record recorded -- closely matches
      Apple's "asleep" and is never below the largest single session;
    - stage fields come from that fullest record (indicative composition)."""
    rows = (
        db.query(HealthSample)
        .filter(HealthSample.metric_name == "sleep_analysis")
        .all()
    )
    groups: dict = {}
    for row in rows:
        payload = row.raw_payload or {}
        key = (payload.get("date") or "")[:10] or _local_date(row.timestamp).isoformat()
        groups.setdefault(key, []).append(row)

    nights = []
    for key, group in groups.items():
        best = max(group, key=lambda r: (r.raw_payload or {}).get("totalSleep") or 0)
        bp = best.raw_payload or {}
        best_total = bp.get("totalSleep") or 0

        intervals, starts, ends = [], [], []
        for r in group:
            p = r.raw_payload or {}
            s, e = _parse_dt(p.get("sleepStart")), _parse_dt(p.get("sleepEnd"))
            if s and e:
                intervals.append((s, e))
                starts.append(s)
                ends.append(e)

        union_h = _merged_hours(intervals)
        bs, be = _parse_dt(bp.get("sleepStart")), _parse_dt(bp.get("sleepEnd"))
        awake_est = 0.0
        if bs and be:
            awake_est = max(0.0, (be - bs).total_seconds() / 3600.0 - best_total)
        total = max(best_total, union_h - awake_est)

        nights.append(
            {
                "date": key,  # wake-date (Apple's label), stable across midnight
                "start": min(starts) if starts else best.timestamp,
                "end": max(ends) if ends else None,
                "total": round(total, 3),
                "deep": bp.get("deep"),
                "core": bp.get("core"),
                "rem": bp.get("rem"),
            }
        )

    nights.sort(key=lambda n: n["start"])
    return nights[-max_nights:]


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
    """For each merged night (a canonical_nights dict), compute this night's
    value for every tracked metric. Returns {metric: [values...]} aligned
    index-for-index with `nights` (None where data is missing)."""
    per_metric = {m: [] for m in OVERNIGHT_METRICS + ["sleep_duration", "resting_heart_rate"]}

    for night in nights:
        sleep_start = night["start"]
        sleep_end = night["end"]
        night_date = date.fromisoformat(night["date"])

        per_metric["sleep_duration"].append(night["total"])
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
