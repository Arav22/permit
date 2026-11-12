"""Real cost tracking using Claude Code's stats-cache.json.

Claude Code writes actual token counts (input, output, cache_read, cache_create)
to ~/.claude/stats-cache.json. We read this to show real costs instead of
per-tool estimates. Delta from session start = real session cost.
"""

import json
import os
import time
from datetime import datetime

_STATS_PATH = os.path.expanduser("~/.claude/stats-cache.json")

# Bedrock pricing per million tokens — calibrated against real Nov 2026 AWS bill
# Claude 4.x is dramatically cheaper than Claude 3.x, especially output tokens
# Opus 4.6 calibrated: $80.43 actual for 94.59M cache_read + 4.35M cache_create + 516K output
_PRICES = {
    "sonnet": {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_create": 3.00},
    "opus":   {"input": 3.0,  "output": 15.0, "cache_read": 0.63, "cache_create": 3.00},
    "haiku":  {"input": 0.80, "output": 4.0,  "cache_read": 0.08, "cache_create": 1.00},
}


def _read_stats() -> dict:
    try:
        with open(_STATS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _model_family(model_key: str) -> str:
    k = model_key.lower()
    if "haiku" in k:
        return "haiku"
    if "sonnet" in k:
        return "sonnet"
    if "opus" in k or "fable" in k:
        return "opus"
    return "sonnet"


def _cost_from_entry(entry: dict, family: str) -> float:
    prices = _PRICES.get(family, _PRICES["sonnet"])
    return (
        (entry.get("inputTokens", 0) / 1e6) * prices["input"] +
        (entry.get("outputTokens", 0) / 1e6) * prices["output"] +
        (entry.get("cacheReadInputTokens", 0) / 1e6) * prices["cache_read"] +
        (entry.get("cacheCreationInputTokens", 0) / 1e6) * prices["cache_create"]
    )


def _total_tokens(entry: dict) -> int:
    return (
        entry.get("inputTokens", 0) +
        entry.get("outputTokens", 0) +
        entry.get("cacheReadInputTokens", 0) +
        entry.get("cacheCreationInputTokens", 0)
    )


def _snapshot_path(session_id: str) -> str:
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    return os.path.join(tmpdir, f"permit-realcost-{session_id}.json")


def get_session_real_cost(session_id: str) -> tuple[float, int]:
    """
    Returns (cost_usd, total_tokens) for the current session by computing
    the delta between session-start snapshot and current stats-cache values.
    """
    if not session_id:
        return 0.0, 0

    current_usage = _read_stats().get("modelUsage", {})
    if not current_usage:
        return 0.0, 0

    snap_path = _snapshot_path(session_id)

    # Load or create session snapshot
    try:
        with open(snap_path) as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # First call this session — save snapshot and return zero delta
        snapshot = {"timestamp": time.time(), "usage": current_usage}
        try:
            with open(snap_path, "w") as f:
                json.dump(snapshot, f)
        except OSError:
            pass
        return 0.0, 0

    start_usage = snapshot.get("usage", {})

    total_cost = 0.0
    total_tok = 0
    for model_key, current in current_usage.items():
        start = start_usage.get(model_key, {})
        delta = {
            "inputTokens":            current.get("inputTokens", 0) - start.get("inputTokens", 0),
            "outputTokens":           current.get("outputTokens", 0) - start.get("outputTokens", 0),
            "cacheReadInputTokens":   current.get("cacheReadInputTokens", 0) - start.get("cacheReadInputTokens", 0),
            "cacheCreationInputTokens": current.get("cacheCreationInputTokens", 0) - start.get("cacheCreationInputTokens", 0),
        }
        # Only count positive deltas (stats can reset or be negative briefly)
        if any(v > 0 for v in delta.values()):
            family = _model_family(model_key)
            total_cost += _cost_from_entry(delta, family)
            total_tok += _total_tokens(delta)

    return max(0.0, total_cost), max(0, total_tok)


def get_today_real_tokens() -> dict[str, int]:
    """Today's total token counts per model — for project report."""
    data = _read_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    for entry in reversed(data.get("dailyModelTokens", [])):
        if entry.get("date") == today:
            return entry.get("tokensByModel", {})
    return {}


def get_all_time_real_cost() -> float:
    """Total real cost across all recorded usage — for project report."""
    usage = _read_stats().get("modelUsage", {})
    return sum(_cost_from_entry(v, _model_family(k)) for k, v in usage.items())


def format_real_cost(cost_usd: float, tokens: int) -> str:
    if tokens >= 1_000_000:
        tok_str = f"{tokens/1_000_000:.1f}M"
    elif tokens >= 1000:
        tok_str = f"{tokens//1000}K"
    else:
        tok_str = str(tokens)

    if cost_usd < 0.001:
        return f"<$0.001 ({tok_str} tok)"
    if cost_usd < 1.0:
        return f"${cost_usd:.3f} ({tok_str} tok)"
    return f"${cost_usd:.2f} ({tok_str} tok)"
