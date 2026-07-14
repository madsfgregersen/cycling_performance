"""LLM cost bookkeeping: the active-model setting, per-call usage recording,
and the daily / by-category aggregations the Logs page reads.

Recording is fail-safe by design -- it opens its own short-lived session and
swallows any error, so a logging hiccup never breaks a coach reply (the whole
point of ai_coach's fail-safe contract)."""

import logging
import os
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from sqlalchemy.orm import Session

from . import llm_pricing
from .database import SessionLocal
from .models import AppConfig, LlmUsage

_logger = logging.getLogger(__name__)

# Match the +9 local day the rest of the app buckets on (see coach_plan_adjust).
LOCAL_TZ = dt_timezone(timedelta(hours=9))

_ACTIVE_MODEL_KEY = "active_model"


def get_active_model(db: Session) -> str:
    """The model the coach should use right now. Athlete-chosen (app_config),
    falling back to the ANTHROPIC_MODEL env default, then the catalog default."""
    try:
        row = db.query(AppConfig).filter(AppConfig.key == _ACTIVE_MODEL_KEY).first()
        if row and llm_pricing.is_known(row.value):
            return row.value
    except Exception:
        _logger.exception("get_active_model failed; using default")
    env_default = os.environ.get("ANTHROPIC_MODEL", "").strip()
    if llm_pricing.is_known(env_default):
        return env_default
    return llm_pricing.DEFAULT_MODEL


def set_active_model(db: Session, model: str) -> None:
    row = db.query(AppConfig).filter(AppConfig.key == _ACTIVE_MODEL_KEY).first()
    if row is None:
        db.add(AppConfig(key=_ACTIVE_MODEL_KEY, value=model))
    else:
        row.value = model
    db.commit()


def record_usage(model: str, category: str, usage) -> None:
    """Persist one call's token usage + computed cost. `usage` is the Anthropic
    response.usage object (or any object exposing the same attributes). Never
    raises."""
    try:
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cost = llm_pricing.cost_usd(model, input_tokens, output_tokens, cache_read, cache_creation)
        db = SessionLocal()
        try:
            db.add(
                LlmUsage(
                    model=model,
                    category=category,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cache_creation_tokens=cache_creation,
                    cost_usd=cost,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        _logger.exception("record_usage failed (non-fatal)")


def _window_rows(db: Session, days: int):
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=days)
    return (
        db.query(LlmUsage)
        .filter(LlmUsage.created_at >= cutoff)
        .all()
    )


def daily_costs(db: Session, days: int = 30) -> list:
    """Cost + call count per local calendar day, oldest first, with empty days
    filled in so the trend reads continuously."""
    rows = _window_rows(db, days)
    by_day = {}
    for r in rows:
        d = r.created_at.astimezone(LOCAL_TZ).date().isoformat() if r.created_at else None
        if d is None:
            continue
        bucket = by_day.setdefault(d, {"cost": 0.0, "calls": 0})
        bucket["cost"] += r.cost_usd or 0.0
        bucket["calls"] += 1

    today = datetime.now(LOCAL_TZ).date()
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        b = by_day.get(d, {"cost": 0.0, "calls": 0})
        out.append({"date": d, "cost": round(b["cost"], 4), "calls": b["calls"]})
    return out


def category_costs(db: Session, days: int = 30) -> list:
    """Cost + call count per workload category, most expensive first."""
    rows = _window_rows(db, days)
    by_cat = {}
    for r in rows:
        bucket = by_cat.setdefault(r.category, {"cost": 0.0, "calls": 0})
        bucket["cost"] += r.cost_usd or 0.0
        bucket["calls"] += 1
    out = [
        {"category": cat, "cost": round(b["cost"], 4), "calls": b["calls"]}
        for cat, b in by_cat.items()
    ]
    out.sort(key=lambda x: x["cost"], reverse=True)
    return out


def report(db: Session, days: int = 30) -> dict:
    daily = daily_costs(db, days)
    return {
        "days": days,
        "active_model": get_active_model(db),
        "models": llm_pricing.options(),
        "daily": daily,
        "by_category": category_costs(db, days),
        "total_cost": round(sum(d["cost"] for d in daily), 4),
        "total_calls": sum(d["calls"] for d in daily),
    }
