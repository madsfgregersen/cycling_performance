from sqlalchemy.orm import Session

from .models import IntegrationLog


def log_event(db: Session, source: str, event: str, summary: str = "") -> None:
    db.add(IntegrationLog(source=source, event=event, summary=summary))
    db.commit()


def recent_events(db: Session, limit: int = 200) -> list:
    rows = (
        db.query(IntegrationLog)
        .order_by(IntegrationLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "timestamp": row.created_at.isoformat() if row.created_at else None,
            "source": row.source,
            "event": row.event,
            "summary": row.summary,
        }
        for row in rows
    ]
