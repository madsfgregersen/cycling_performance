from typing import Optional

from sqlalchemy.orm import Session

from .models import RideStream

# Below this many paired watts/heartrate seconds, a first-half/second-half
# split is too noisy to call decoupling -- report nothing rather than a
# number that doesn't mean anything (no invented numbers).
MIN_PAIRED_SECONDS_FOR_DECOUPLING = 20 * 60


def _efficiency_factor(ride) -> Optional[float]:
    power = ride.weighted_avg_watts or ride.average_watts
    if not power or not ride.average_heartrate:
        return None
    return round(power / ride.average_heartrate, 2)


def _ratio(chunk) -> Optional[float]:
    avg_power = sum(p for p, _ in chunk) / len(chunk)
    avg_hr = sum(h for _, h in chunk) / len(chunk)
    return avg_power / avg_hr if avg_hr else None


def _decoupling_pct(db: Session, ride_id: int) -> Optional[float]:
    rows = (
        db.query(RideStream.watts, RideStream.heartrate)
        .filter(RideStream.ride_id == ride_id)
        .order_by(RideStream.second_offset)
        .all()
    )
    paired = [(watts, hr) for watts, hr in rows if watts and hr]
    if len(paired) < MIN_PAIRED_SECONDS_FOR_DECOUPLING:
        return None

    half = len(paired) // 2
    first_half_ratio = _ratio(paired[:half])
    second_half_ratio = _ratio(paired[half:])
    if not first_half_ratio or not second_half_ratio:
        return None

    # Positive = heart rate drifted up relative to power in the second half
    # (a fade). Negative would mean the opposite -- efficiency held or improved.
    return round((first_half_ratio - second_half_ratio) / first_half_ratio * 100, 1)


def compute_ride_metrics(db: Session, ride) -> dict:
    return {
        "efficiency_factor": _efficiency_factor(ride),
        "decoupling_pct": _decoupling_pct(db, ride.id),
    }
