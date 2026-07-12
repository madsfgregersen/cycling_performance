import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import DailyReadiness, PlannedWorkout, RideSummary

FTP_WATTS = float(os.environ.get("FTP_WATTS", "315"))

CTL_DAYS = 42
ATL_DAYS = 7


def _compute_ride_tss(ride: RideSummary):
    power = ride.weighted_avg_watts or ride.average_watts
    if not power or not ride.moving_time_s:
        return None
    intensity_factor = power / FTP_WATTS
    return (ride.moving_time_s * power * intensity_factor) / (FTP_WATTS * 3600) * 100


def _verdict(tsb: float) -> str:
    if tsb > -10:
        return "green"
    if tsb > -30:
        return "amber"
    return "red"


def recompute(db: Session) -> dict:
    rides = db.query(RideSummary).order_by(RideSummary.start_date).all()
    if not rides:
        return {"rides_updated": 0, "days_computed": 0}

    daily_tss = defaultdict(float)
    rides_updated = 0
    for ride in rides:
        tss = _compute_ride_tss(ride)
        if tss is not None:
            ride.ride_tss = tss
            rides_updated += 1
            daily_tss[ride.start_date.date()] += tss
    db.commit()

    start = min(ride.start_date.date() for ride in rides)
    today = date.today()

    ctl = 0.0
    atl = 0.0
    days_computed = 0
    current = start
    while current <= today:
        tss_today = daily_tss.get(current, 0.0)
        tsb = ctl - atl
        ctl = ctl + (tss_today - ctl) / CTL_DAYS
        atl = atl + (tss_today - atl) / ATL_DAYS

        row = db.query(DailyReadiness).filter(DailyReadiness.date == current).first()
        if row is None:
            row = DailyReadiness(date=current)
            db.add(row)
        row.ctl = ctl
        row.atl = atl
        row.tsb = tsb
        row.verdict = _verdict(tsb)
        row.computed_at = datetime.now(timezone.utc)

        days_computed += 1
        current += timedelta(days=1)

    db.commit()
    return {"rides_updated": rides_updated, "days_computed": days_computed}


def project_forward(db: Session, horizon_days: int = 14) -> list:
    # Compute-on-demand only, per the locked architecture -- never written
    # back to daily_readiness (Bucket 5 is sacred, actual history only).
    latest = db.query(DailyReadiness).order_by(DailyReadiness.date.desc()).first()
    if latest is None:
        return []

    end_date = latest.date + timedelta(days=horizon_days)
    planned = (
        db.query(PlannedWorkout)
        .filter(PlannedWorkout.date > latest.date, PlannedWorkout.date <= end_date)
        .all()
    )
    planned_tss_by_date = defaultdict(float)
    for workout in planned:
        planned_tss_by_date[workout.date] += workout.target_tss or 0.0

    ctl = latest.ctl or 0.0
    atl = latest.atl or 0.0
    current = latest.date
    projection = []
    for _ in range(horizon_days):
        current += timedelta(days=1)
        tss_today = planned_tss_by_date.get(current, 0.0)
        tsb = ctl - atl
        ctl = ctl + (tss_today - ctl) / CTL_DAYS
        atl = atl + (tss_today - atl) / ATL_DAYS

        projection.append(
            {"date": current.isoformat(), "ctl": ctl, "atl": atl, "tsb": tsb}
        )

    return projection
