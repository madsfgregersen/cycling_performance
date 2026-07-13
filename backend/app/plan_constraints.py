from sqlalchemy.orm import Session

from .models import PlanConstraint


def list_constraints(db: Session, active_only: bool = True) -> list:
    query = db.query(PlanConstraint)
    if active_only:
        query = query.filter(PlanConstraint.active == True)  # noqa: E712
    rows = query.order_by(PlanConstraint.created_at).all()
    return [{"id": r.id, "text": r.text, "active": r.active} for r in rows]


def add_constraint(db: Session, text: str) -> dict:
    row = PlanConstraint(text=text, active=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "text": row.text, "active": row.active}


def deactivate_constraint(db: Session, constraint_id: int) -> dict:
    row = db.query(PlanConstraint).filter(PlanConstraint.id == constraint_id).first()
    if row is None:
        return {"error": "not found"}
    row.active = False
    db.commit()
    return {"id": row.id, "active": False}
