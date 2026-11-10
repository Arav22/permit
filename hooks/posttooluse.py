#!/usr/bin/env python3
"""PostToolUse hook — records completed tool calls for session tracking."""

import json
import os
import sys

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

try:
    from core.analyzer import analyze_tool
    from core.tracker import record_event
    from core.config import load_config
    from core.cost import estimate_cost
    from core.rollback import _load_manifest
    from core.project_tracker import update_session
except ImportError:
    print(json.dumps({}))
    sys.exit(0)


def _find_snapshot_id(tool_use_id: str) -> str | None:
    """Find snapshot created by PreToolUse for this same tool call."""
    if not tool_use_id:
        return None
    manifest = _load_manifest()
    for sid, data in manifest.items():
        if data.get("tool_use_id") == tool_use_id:
            return sid
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_use_id = input_data.get("tool_use_id", "")

    analysis = analyze_tool(tool_name, tool_input)
    if analysis is None:
        print(json.dumps({}))
        sys.exit(0)

    config = load_config()
    cost_usd = 0.0
    if config.cost.enabled:
        est = estimate_cost(tool_name, tool_input, config.cost.model)
        cost_usd = est.cost_usd

    snapshot_id = _find_snapshot_id(tool_use_id)

    file_path = tool_input.get("file_path")
    record_event(
        tool_name=tool_name,
        summary=analysis.title,
        file_path=file_path,
        risk=analysis.risk,
        cost_estimate_usd=cost_usd,
        snapshot_id=snapshot_id,
    )

    try:
        update_session(
            tool_name=tool_name,
            file_path=file_path or "",
            risk=analysis.risk,
            cost_usd=cost_usd,
            model=config.cost.model,
            patterns=[],
        )
    except Exception:
        pass

    print(json.dumps({}))
    sys.exit(0)


if __name__ == "__main__":
    main()
