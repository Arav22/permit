#!/usr/bin/env python3
"""PreToolUse hook — analyzes tool calls and shows plain-English explanations."""

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
    from core.tracker import get_chain, get_history, format_chain, get_session_cost
    from core.formatter import format_explanation, format_compact
    from core.config import load_config, should_show, should_snapshot
    from core.patterns import detect_workflow, detect_file_heat
    from core.cost import estimate_cost
    from core.rollback import create_snapshot, ensure_gitignore
    from core.coach import detect_patterns
    from core.discovery import detect_hints
    from core.cost import _detect_model
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
    tool_use_id = input_data.get("tool_use_id", "")

    config = load_config()
    analysis = analyze_tool(tool_name, tool_input)

    if analysis is None or not should_show(config, analysis.risk):
        print(json.dumps({}))
        sys.exit(0)

    file_path = tool_input.get("file_path")
    history = get_history()

    workflow = detect_workflow(history, tool_name, analysis.title, file_path)
    heat = detect_file_heat(history, file_path) if file_path else 0

    chain_text = ""
    if config.show_history:
        chain = get_chain(limit=3)
        if chain:
            chain_text = format_chain(chain, analysis.title)

    # Auto-detect model when not explicitly configured
    active_model = config.cost.model or _detect_model()

    cost_estimate = None
    session_cost = 0.0
    if config.cost.enabled:
        cost_estimate = estimate_cost(tool_name, tool_input, active_model)
        if not config.cost.show_per_operation:
            cost_estimate = None
        if config.cost.show_session_total:
            session_cost = get_session_cost()
            if cost_estimate:
                session_cost += cost_estimate.cost_usd
        if cost_estimate and not config.cost.show_tips:
            cost_estimate.tips = []

    snapshot_saved = False
    if tool_name in ("Edit", "Write") and file_path:
        if should_snapshot(config, analysis.risk):
            sid = create_snapshot(
                file_path,
                analysis.title,
                max_file_size=config.rollback.max_file_size_bytes,
                tool_use_id=tool_use_id,
            )
            if sid:
                snapshot_saved = True
                gi_warn = ensure_gitignore()
                if gi_warn:
                    analysis.warnings.append(gi_warn)

    coaching = []
    if config.coach.enabled and config.verbosity not in ("minimal",):
        # Coach shown for caution and danger; not for safe (compact line = no room)
        if analysis.risk in ("caution", "danger"):
            coaching = detect_patterns(
                tool_name, tool_input, history,
                active_model, os.getcwd(),
                max_tips=config.coach.max_tips_per_box,
            )

    hints = []
    if config.coach.enabled:
        hints = detect_hints(tool_name, tool_input, history, snapshot_saved, os.getcwd())

    # Smart verbosity: scale box size by risk
    if config.verbosity == "smart":
        if analysis.risk == "safe":
            message = format_compact(analysis, workflow=workflow, cost=cost_estimate, hints=hints)
        elif analysis.risk == "caution":
            message = format_explanation(
                analysis,
                workflow=workflow,
                file_heat=heat,
                verbosity="normal",
                cost=cost_estimate,
                session_cost_usd=session_cost,
                snapshot_saved=snapshot_saved,
                budget_usd=config.cost.budget_usd,
                coaching=coaching,
                hints=hints,
            )
        else:
            message = format_explanation(
                analysis,
                related_chain=chain_text if config.show_diagram else "",
                workflow=workflow,
                file_heat=heat,
                verbosity="normal",
                cost=cost_estimate,
                session_cost_usd=session_cost,
                snapshot_saved=snapshot_saved,
                budget_usd=config.cost.budget_usd,
                coaching=coaching,
                hints=hints,
            )
    elif config.verbosity == "minimal":
        message = format_compact(analysis, workflow=workflow, cost=cost_estimate)
    else:
        message = format_explanation(
            analysis,
            related_chain=chain_text if config.show_diagram else "",
            workflow=workflow,
            file_heat=heat,
            verbosity=config.verbosity,
            cost=cost_estimate,
            session_cost_usd=session_cost,
            snapshot_saved=snapshot_saved,
            budget_usd=config.cost.budget_usd,
            coaching=coaching,
            hints=hints,
        )

    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    main()
