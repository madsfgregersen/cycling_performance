"""Single source of truth for the athlete's local timezone.

DST-aware (Europe/Copenhagen = CET in winter, CEST in summer), configurable
via the APP_TIMEZONE env var so a move or travel is a config change, not a
deploy. Replaces the old hardcoded UTC+9 offset, which mislabelled the local
day: an evening health-sync rolled over into the next Japan-day, so the
morning verdict was delivered in the evening and then skipped the next morning.
"""
import os

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover -- Python < 3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore

# .strip() guards against whitespace in a pasted Railway env var.
LOCAL_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Europe/Copenhagen").strip())
