#!/usr/bin/env python3
"""PreToolUse hook — analyzes tool calls and shows plain-English explanations."""

import json
import os
import sys

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

try:
    from core.analyzer import analyze_tool
    from core.tracker import find_related, get_chain, format_chain
    from core.formatter import format_explanation, format_compact
    from core.config import load_config, should_show
except ImportError as e:
    print(json.dumps({"systemMessage": f"[permit] import error: {e}"}))
    sys.exit(0)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({}))
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    config = load_config()
    analysis = analyze_tool(tool_name, tool_input)

    if analysis is None or not should_show(config, analysis.risk):
        print(json.dumps({}))
        sys.exit(0)

    file_path = tool_input.get("file_path")
    chain_text = ""

    if config.show_history:
        chain = get_chain(limit=3)
        if chain:
            chain_text = format_chain(chain, analysis.title)

    if config.verbosity == "minimal":
        message = format_compact(analysis)
    else:
        message = format_explanation(
            analysis,
            related_chain=chain_text if config.show_diagram else "",
            verbosity=config.verbosity,
        )

    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    main()
