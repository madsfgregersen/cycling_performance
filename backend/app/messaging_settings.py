from sqlalchemy.orm import Session

from .models import MessagingSetting

# The proactive/push-style messages defined in docs/coach-brief.md.
# Reactive things (answer a question, co-design the plan) aren't here --
# there's nothing to toggle off, the coach just responds when messaged.
# `built` reflects what's actually wired to send today; toggles for
# not-yet-built entries just store the preference for when they are.
CATALOG = [
    {
        "key": "morning_verdict",
        "label": "Morning verdict & check-in",
        "description": "Explains today's readiness verdict and asks freshness / work-life stress.",
        "story": "1 + 2",
        "built": True,
    },
    {
        "key": "post_ride_debrief",
        "label": "Post-ride debrief",
        "description": "Interprets a finished ride (EF, decoupling, late-ride fade) against what it was for.",
        "story": "3",
        "built": True,
    },
    {
        "key": "ride_feel_ask",
        "label": "Ride feel / RPE ask",
        "description": "Asks how a ride felt so subjective and objective data sit together.",
        "story": "4",
        "built": True,
    },
    {
        "key": "missed_workout_nudge",
        "label": "Missed workout nudge",
        "description": "Flags a missed session without silently stacking it onto a later day.",
        "story": "5",
        "built": True,
    },
    {
        "key": "constraint_drift_alert",
        "label": "Constraint drift alert",
        "description": "Flags when reality has drifted from the athlete's stated constraints.",
        "story": "8",
        "built": True,
    },
    {
        "key": "weekly_summary",
        "label": "Weekly / block summary",
        "description": "Wrap-up of how the week or block actually went.",
        "story": "9",
        "built": True,
    },
    {
        "key": "on_track_check",
        "label": "\"On track for event\" check",
        "description": "Compares trajectory to what the target event demands.",
        "story": "10",
        "built": False,
    },
]

_KEYS = {entry["key"] for entry in CATALOG}


def list_settings(db: Session) -> list:
    rows = {row.key: row.enabled for row in db.query(MessagingSetting).all()}
    return [{**entry, "enabled": rows.get(entry["key"], True)} for entry in CATALOG]


def is_enabled(db: Session, key: str) -> bool:
    row = db.query(MessagingSetting).filter(MessagingSetting.key == key).first()
    return row.enabled if row is not None else True


def set_enabled(db: Session, key: str, enabled: bool) -> dict:
    if key not in _KEYS:
        return {"error": "unknown key"}
    row = db.query(MessagingSetting).filter(MessagingSetting.key == key).first()
    if row is None:
        row = MessagingSetting(key=key, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    db.commit()
    return {"key": key, "enabled": enabled}
