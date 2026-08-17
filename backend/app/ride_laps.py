import time
from collections import deque

from sqlalchemy.orm import Session

from . import strava
from .activity_log import log_event
from .models import RideLap, RideStream, RideSummary
from .readiness import FTP_WATTS

# Coggan power-zone boundaries as a fraction of FTP (upper edge). Anything at
# or above the z5 floor is z5 (VO2 and above folded together).
_ZONE_EDGES = [(0.55, "z1"), (0.75, "z2"), (0.90, "z3"), (1.05, "z4")]

NP_WINDOW_S = 30


def _zone(np_value):
    if np_value is None:
        return None
    ratio = np_value / FTP_WATTS
    for edge, label in _ZONE_EDGES:
        if ratio < edge:
            return label
    return "z5"


def _normalized_power(watts: list):
    """Normalized power: 30 s rolling average of power, raised to the 4th
    power, averaged, 4th-rooted. Falls back to the plain mean for laps shorter
    than the window (a short rep is steady enough that NP == avg)."""
    vals = [w for w in watts if w is not None]
    if not vals:
        return None
    if len(vals) < NP_WINDOW_S:
        return sum(vals) / len(vals)
    window = deque()
    window_sum = 0.0
    fourth_powers = []
    for w in vals:
        window.append(w)
        window_sum += w
        if len(window) > NP_WINDOW_S:
            window_sum -= window.popleft()
        if len(window) == NP_WINDOW_S:
            fourth_powers.append((window_sum / NP_WINDOW_S) ** 4)
    if not fourth_powers:
        return sum(vals) / len(vals)
    return (sum(fourth_powers) / len(fourth_powers)) ** 0.25


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _compute_lap_metrics(samples: list) -> dict:
    duration_s = len(samples)  # 1 Hz streams -> one sample per second
    watts = [s.watts for s in samples]
    np_value = _normalized_power(watts)
    intensity_factor = np_value / FTP_WATTS if np_value else None
    lap_tss = (
        (duration_s * np_value * intensity_factor) / (FTP_WATTS * 3600) * 100
        if np_value and intensity_factor
        else None
    )
    return {
        "avg_power": _avg(watts),
        "normalized_power": round(np_value, 1) if np_value else None,
        "max_power": _max(watts),
        "avg_hr": _avg([s.heartrate for s in samples]),
        "max_hr": _max([s.heartrate for s in samples]),
        "avg_cadence": _avg([s.cadence for s in samples]),
        "avg_speed": _avg([s.velocity_smooth for s in samples]),
        "intensity_factor": round(intensity_factor, 3) if intensity_factor else None,
        "lap_tss": round(lap_tss, 1) if lap_tss else None,
        "intensity_zone": _zone(np_value),
    }


def sync_ride_laps(db: Session, ride: RideSummary) -> dict:
    """Fetch the ride's laps from Strava and (re)compute one RideLap row per
    lap from this ride's stored stream slice. Idempotent -- replaces any
    existing laps for the ride."""
    laps = strava.get_activity_laps(db, ride.strava_activity_id)
    if not laps:
        return {"laps": 0, "reason": "no laps"}

    streams = (
        db.query(RideStream)
        .filter(RideStream.ride_id == ride.id)
        .order_by(RideStream.second_offset)
        .all()
    )
    if not streams:
        return {"laps": 0, "reason": "no streams"}

    db.query(RideLap).filter(RideLap.ride_id == ride.id).delete()

    saved = 0
    for i, lap in enumerate(laps):
        start_index = lap.get("start_index")
        end_index = lap.get("end_index")
        if start_index is None or end_index is None:
            continue
        # start_index/end_index are positions into the stream arrays, which we
        # stored one row per sample in time order.
        segment = streams[start_index : end_index + 1]
        if not segment:
            continue
        metrics = _compute_lap_metrics(segment)
        db.add(
            RideLap(
                ride_id=ride.id,
                lap_index=i,
                start_offset_s=segment[0].second_offset,
                end_offset_s=segment[-1].second_offset,
                name=lap.get("name"),
                distance_m=lap.get("distance"),
                moving_time_s=lap.get("moving_time"),
                elapsed_time_s=lap.get("elapsed_time"),
                elevation_gain_m=lap.get("total_elevation_gain"),
                **metrics,
            )
        )
        saved += 1

    db.commit()
    return {"laps": saved}


def backfill_laps(db: Session) -> dict:
    """One-off: populate laps for every ride already stored. Rate-limited to
    stay under Strava's limit (one laps call per ride)."""
    rides = db.query(RideSummary).order_by(RideSummary.start_date).all()
    total_laps = 0
    rides_with_laps = 0
    for ride in rides:
        try:
            result = sync_ride_laps(db, ride)
        except Exception:
            continue
        if result.get("laps"):
            total_laps += result["laps"]
            rides_with_laps += 1
        time.sleep(0.3)
    log_event(
        db,
        "strava_backfill",
        "laps_backfilled",
        f"{rides_with_laps} rides, {total_laps} laps",
    )
    return {"rides_with_laps": rides_with_laps, "total_laps": total_laps, "rides_scanned": len(rides)}
