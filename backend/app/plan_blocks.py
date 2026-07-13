from datetime import date

from sqlalchemy.orm import Session

from .models import PlanBlock


def _serialize(row: PlanBlock) -> dict:
    return {
        "week": row.week,
        "start": row.start_date.isoformat(),
        "end": row.end_date.isoformat(),
        "phase": row.phase,
        "label": row.label,
        "focus": row.focus,
        "detail": row.detail,
    }


def list_blocks(db: Session) -> list:
    rows = db.query(PlanBlock).order_by(PlanBlock.week).all()
    return [_serialize(r) for r in rows]


def get_block(db: Session, week: int):
    row = db.query(PlanBlock).filter(PlanBlock.week == week).first()
    return _serialize(row) if row else None


def current_block(db: Session, today: date):
    row = (
        db.query(PlanBlock)
        .filter(PlanBlock.start_date <= today, PlanBlock.end_date >= today)
        .first()
    )
    return _serialize(row) if row else None


def taper_week(db: Session):
    row = db.query(PlanBlock).filter(PlanBlock.phase == "taper").first()
    return _serialize(row) if row else None


def update_block(db: Session, week: int, phase=None, label=None, focus=None, detail=None) -> bool:
    row = db.query(PlanBlock).filter(PlanBlock.week == week).first()
    if row is None:
        return False
    if phase is not None:
        row.phase = phase
    if label is not None:
        row.label = label
    if focus is not None:
        row.focus = focus
    if detail is not None:
        row.detail = detail
    db.commit()
    return True
