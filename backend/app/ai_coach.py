import json
import logging
import os

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
_logger = logging.getLogger(__name__)


def _active_model() -> str:
    """The model to call, chosen from the dashboard (DB) with env/default
    fallback. Read per call so a model switch takes effect immediately, with
    no redeploy. Fail-safe: any error falls back to the catalog default."""
    from . import llm_pricing, llm_usage
    from .database import SessionLocal

    try:
        db = SessionLocal()
        try:
            return llm_usage.get_active_model(db)
        finally:
            db.close()
    except Exception:
        _logger.exception("_active_model failed; using default")
        return llm_pricing.DEFAULT_MODEL


def ask_claude(prompt: str, system: str = None, max_tokens: int = 1024, category: str = "uncategorized") -> str:
    """Send a single prompt to Claude and return its text response.

    Pure plumbing -- no coaching prompt or behavior lives here. `system` is
    optional so this still works for non-coaching callers (e.g. the plain
    connectivity ping). Returns an empty string if ANTHROPIC_API_KEY isn't
    configured, rather than raising, matching the rest of this app's pattern
    for optional integrations. Also fails safe (empty string) on a transient
    API error -- callers up the chain (e.g. Telegram's webhook) must never
    500 out and go silent just because one API call hiccuped.
    """
    if _client is None:
        return ""

    try:
        from . import llm_usage

        model = _active_model()
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = _client.messages.create(**kwargs)
        llm_usage.record_usage(model, category, response.usage)
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception:
        _logger.exception("ask_claude failed")
        return ""


def ask_claude_structured(prompt: str, system: str, schema: dict, max_tokens: int = 1024, category: str = "uncategorized") -> dict:
    """Like ask_claude, but constrains the response to the given JSON schema
    and returns the parsed object. Returns {} if not configured, or if the
    call fails or the response doesn't parse -- same fail-safe reasoning as
    ask_claude above."""
    if _client is None:
        return {}

    try:
        from . import llm_usage

        model = _active_model()
        response = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        llm_usage.record_usage(model, category, response.usage)
        text = "".join(block.text for block in response.content if block.type == "text")
        return json.loads(text) if text else {}
    except Exception:
        _logger.exception("ask_claude_structured failed")
        return {}
