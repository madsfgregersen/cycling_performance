from sqlalchemy.orm import Session

from . import plan_blocks, race_goal


def get_overview(db: Session) -> dict:
    return {"goal": race_goal.get_goal(db), "weeks": plan_blocks.list_blocks(db)}
