import json
import os

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8").strip()

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


def ask_claude(prompt: str, max_tokens: int = 1024) -> str:
    """Send a single prompt to Claude and return its text response.

    Pure plumbing -- no coaching prompt or behavior lives here. Returns an
    empty string if ANTHROPIC_API_KEY isn't configured, rather than raising,
    matching the rest of this app's pattern for optional integrations.
    """
    if _client is None:
        return ""

    response = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def ask_claude_structured(prompt: str, system: str, schema: dict, max_tokens: int = 1024) -> dict:
    """Like ask_claude, but constrains the response to the given JSON schema
    and returns the parsed object. Returns {} if not configured."""
    if _client is None:
        return {}

    response = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(text) if text else {}
