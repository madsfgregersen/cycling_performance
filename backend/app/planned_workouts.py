from sqlalchemy.orm import Session

from .models import PlannedWorkout


def _serialize(row: PlannedWorkout) -> dict:
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "target_tss": row.target_tss,
        "notes": row.notes,
    }


def list_workouts(db: Session) -> list:
    rows = db.query(PlannedWorkout).order_by(PlannedWorkout.date).all()
    return [_serialize(row) for row in rows]


def create_workout(db: Session, workout_date, target_tss, notes) -> dict:
    workout = PlannedWorkout(date=workout_date, target_tss=target_tss, notes=notes)
    db.add(workout)
    db.commit()
    db.refresh(workout)
    return _serialize(workout)


def update_workout(db: Session, workout_id: int, workout_date, target_tss, notes):
    workout = db.query(PlannedWorkout).filter(PlannedWorkout.id == workout_id).first()
    if workout is None:
        return None
    workout.date = workout_date
    workout.target_tss = target_tss
    workout.notes = notes
    db.commit()
    db.refresh(workout)
    return _serialize(workout)


def delete_workout(db: Session, workout_id: int) -> dict:
    workout = db.query(PlannedWorkout).filter(PlannedWorkout.id == workout_id).first()
    if workout is None:
        return {"deleted": False}
    db.delete(workout)
    db.commit()
    return {"deleted": True}
