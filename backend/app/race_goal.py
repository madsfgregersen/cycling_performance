from sqlalchemy.orm import Session

from .models import RaceGoal


def _serialize(row: RaceGoal) -> dict:
    return {
        "name": row.name,
        "date": row.date.isoformat(),
        "distance_km": row.distance_km,
        "elevation_m": row.elevation_m,
        "hills": row.hills,
    }


def get_goal(db: Session) -> dict:
    row = db.query(RaceGoal).first()
    return _serialize(row)


def update_goal(db: Session, name=None, date=None, distance_km=None, elevation_m=None, hills=None) -> dict:
    row = db.query(RaceGoal).first()
    if name is not None:
        row.name = name
    if date is not None:
        row.date = date
    if distance_km is not None:
        row.distance_km = distance_km
    if elevation_m is not None:
        row.elevation_m = elevation_m
    if hills is not None:
        row.hills = hills
    db.commit()
    return _serialize(row)
