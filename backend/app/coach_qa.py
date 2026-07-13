import json

from sqlalchemy.orm import Session

from . import ai_coach, coach_context
from .coach_voice import COACH_SYSTEM_PROMPT

HISTORY_MESSAGES = 10


def answer_question(db: Session, question: str, recent_thread: list) -> str:
    """Plain-text, grounded answer to a question about the athlete's own
    data. Read-only -- never proposes or writes anything, unlike the
    disruption/plan-structure branches. Recent thread messages are passed
    in so a follow-up ("and compared to last week?") reads like a real
    conversation rather than a one-shot Q&A."""
    context = coach_context.get_coach_context(db)

    history_lines = [
        f"{'Athlete' if m['role'] == 'athlete' else 'Coach'}: {m['text']}"
        for m in recent_thread[-HISTORY_MESSAGES:]
    ]
    history_block = "\n".join(history_lines) if history_lines else "(no recent conversation)"

    prompt = (
        "Here is the athlete's current data:\n\n"
        + json.dumps(context, indent=2)
        + "\n\nRecent conversation, for context:\n"
        + history_block
        + f'\n\nThe athlete just asked: "{question}"\n\n'
        "Answer using only the data given above -- never estimate or invent a "
        "figure you weren't given. If something needed to answer isn't in the "
        "data, say so plainly rather than guessing. Keep it conversational, "
        "not a report."
    )
    return ai_coach.ask_claude(prompt, system=COACH_SYSTEM_PROMPT)
