"""LLM model catalog + cost math -- the single source of truth for both the
model switcher dropdown and the cost computed on every recorded call.

Prices are USD per million tokens, from Anthropic's published pricing
(https://platform.claude.com/docs/en/about-claude/models/overview). Cache
reads bill at ~0.1x input; cache writes (5-minute TTL) at ~1.25x input. Update
this table if Anthropic changes pricing -- everything else derives from it."""

# Ordered most- to least-capable; this order drives the dropdown.
MODELS = [
    {"id": "claude-opus-4-8", "label": "Opus 4.8 (most capable)", "input": 5.0, "output": 25.0},
    {"id": "claude-sonnet-5", "label": "Sonnet 5 (~40% cheaper)", "input": 3.0, "output": 15.0},
    {"id": "claude-haiku-4-5", "label": "Haiku 4.5 (~80% cheaper)", "input": 1.0, "output": 5.0},
]

DEFAULT_MODEL = "claude-opus-4-8"

_BY_ID = {m["id"]: m for m in MODELS}

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25


def is_known(model: str) -> bool:
    return model in _BY_ID


def label_for(model: str) -> str:
    m = _BY_ID.get(model)
    return m["label"] if m else model


def options() -> list:
    """The switchable models, for the dashboard dropdown."""
    return [
        {"id": m["id"], "label": m["label"], "input_per_m": m["input"], "output_per_m": m["output"]}
        for m in MODELS
    ]


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float:
    """Cost of one call in USD. Unknown models cost 0 (we still record the
    token counts, so the row isn't lost -- just add the model to MODELS to
    price it retroactively in reports)."""
    m = _BY_ID.get(model)
    if m is None:
        return 0.0
    in_rate = m["input"] / 1_000_000
    out_rate = m["output"] / 1_000_000
    return (
        input_tokens * in_rate
        + output_tokens * out_rate
        + cache_read_tokens * in_rate * CACHE_READ_MULTIPLIER
        + cache_creation_tokens * in_rate * CACHE_WRITE_MULTIPLIER
    )
