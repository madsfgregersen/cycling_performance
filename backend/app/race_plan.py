from sqlalchemy.orm import Session

from . import plan_blocks

# The event itself -- fixed facts, not something to co-design. The 7-week
# block structure that used to be hardcoded here now lives in plan_blocks
# (docs/coach-brief.md story 7 -- it needed to become genuinely editable).
GOAL = {
    "name": "Geo Park Gran Fondo",
    "date": "2026-08-30",
    "distance_km": 150,
    "elevation_m": 2000,
    "hills": 12,
}


def get_overview(db: Session) -> dict:
    return {"goal": GOAL, "weeks": plan_blocks.list_blocks(db)}
