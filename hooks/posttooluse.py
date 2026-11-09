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
except ImportError:
    print(json.dumps({}))
    sys.exit(0)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    analysis = analyze_tool(tool_name, tool_input)
    if analysis is None:
        print(json.dumps({}))
        sys.exit(0)

    file_path = tool_input.get("file_path")
    record_event(
        tool_name=tool_name,
        summary=analysis.title,
        file_path=file_path,
        risk=analysis.risk,
    )

    print(json.dumps({}))
    sys.exit(0)


if __name__ == "__main__":
    main()
