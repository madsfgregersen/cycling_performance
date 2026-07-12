import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from . import strava
from .models import RideStream, RideSummary

ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STREAM_KEYS = "time,watts,heartrate,cadence,altitude,velocity_smooth,distance,latlng"
BACKFILL_DAYS = 60


def _fetch_activities(db: Session) -> list[dict]:
    access_token = strava.get_valid_access_token(db)
    headers = {"Authorization": f"Bearer {access_token}"}
    after = int((datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)).timestamp())

    activities = []
    page = 1
    while True:
        response = httpx.get(
            ACTIVITIES_URL,
            headers=headers,
            params={"after": after, "per_page": 100, "page": page},
            timeout=15,
        )
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1

    return [activity for activity in activities if activity.get("type") == "Ride"]


def _fetch_streams(db: Session, activity_id: int) -> dict:
    access_token = strava.get_valid_access_token(db)
    headers = {"Authorization": f"Bearer {access_token}"}
    response = httpx.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}/streams",
        headers=headers,
        params={"keys": STREAM_KEYS, "key_by_type": "true"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _save_ride_summary(db: Session, activity: dict) -> RideSummary:
    start_date = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
    ride = RideSummary(
        strava_activity_id=activity["id"],
        name=activity.get("name"),
        start_date=start_date,
        distance_m=activity.get("distance"),
        moving_time_s=activity.get("moving_time"),
        elapsed_time_s=activity.get("elapsed_time"),
        elevation_gain_m=activity.get("total_elevation_gain"),
        average_watts=activity.get("average_watts"),
        weighted_avg_watts=activity.get("weighted_average_watts"),
        average_heartrate=activity.get("average_heartrate"),
        max_heartrate=activity.get("max_heartrate"),
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


def _save_ride_streams(db: Session, ride_id: int, streams: dict) -> int:
    time_stream = streams.get("time", {}).get("data")
    if not time_stream:
        return 0

    def series(key):
        return streams.get(key, {}).get("data")

    watts = series("watts")
    heartrate = series("heartrate")
    cadence = series("cadence")
    altitude = series("altitude")
    velocity = series("velocity_smooth")
    distance = series("distance")
    latlng = series("latlng")

    rows = []
    for i, offset in enumerate(time_stream):
        lat, lng = latlng[i] if latlng else (None, None)
        rows.append(
            RideStream(
                ride_id=ride_id,
                second_offset=offset,
                watts=watts[i] if watts else None,
                heartrate=heartrate[i] if heartrate else None,
                cadence=cadence[i] if cadence else None,
                altitude=altitude[i] if altitude else None,
                velocity_smooth=velocity[i] if velocity else None,
                distance=distance[i] if distance else None,
                latitude=lat,
                longitude=lng,
            )
        )

    db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def ingest_single_activity(db: Session, activity_id: int) -> dict:
    activity = strava.get_activity(db, activity_id)
    if activity.get("type") != "Ride":
        return {"imported": False, "reason": "not a Ride"}

    exists = (
        db.query(RideSummary)
        .filter(RideSummary.strava_activity_id == activity_id)
        .first()
    )
    if exists:
        return {"imported": False, "reason": "already exists"}

    ride = _save_ride_summary(db, activity)
    streams = _fetch_streams(db, activity_id)
    stream_rows = _save_ride_streams(db, ride.id, streams)
    return {"imported": True, "stream_rows_saved": stream_rows}


def delete_activity(db: Session, activity_id: int) -> dict:
    ride = (
        db.query(RideSummary)
        .filter(RideSummary.strava_activity_id == activity_id)
        .first()
    )
    if ride is None:
        return {"deleted": False}

    db.query(RideStream).filter(RideStream.ride_id == ride.id).delete()
    db.delete(ride)
    db.commit()
    return {"deleted": True}


def run_backfill(db: Session) -> dict:
    activities = _fetch_activities(db)

    imported = 0
    skipped = 0
    stream_rows = 0

    for activity in activities:
        exists = (
            db.query(RideSummary)
            .filter(RideSummary.strava_activity_id == activity["id"])
            .first()
        )
        if exists:
            skipped += 1
            continue

        ride = _save_ride_summary(db, activity)
        streams = _fetch_streams(db, activity["id"])
        stream_rows += _save_ride_streams(db, ride.id, streams)
        imported += 1
        time.sleep(0.5)  # stay comfortably under Strava's rate limit

    return {
        "found": len(activities),
        "imported": imported,
        "skipped_existing": skipped,
        "stream_rows_saved": stream_rows,
    }
