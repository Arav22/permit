#!/usr/bin/env python3
"""
permit v4.2 demo — simulates a realistic coding session.

Shows all features:
  - Smart verbosity: compact for safe, full box for caution/danger
  - COACH: anti-pattern tips (full_test_run, chained_destructive, etc.)
  - HINT: command discovery (contextual one-liners)
  - "Why:" intent line from workflow context
  - Budget bar
  - OBS: obsolete pattern detection (yellow)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Demo mode: bypass suppression so every feature fires ---
import core.discovery as _disc
import core.coach as _coach
_disc._hint_seen_count = lambda hid: 0
_disc._record_hint = lambda hid: None
_coach.record_pattern = lambda pid: None
_coach.format_trajectory = lambda pid: ""
# -----------------------------------------------------------

from core.analyzer import analyze_tool
from core.cost import estimate_cost
from core.formatter import format_explanation, format_compact
from core.patterns import detect_workflow, detect_file_heat
from core.tracker import format_chain
from core.coach import detect_patterns
from core.discovery import detect_hints
from core.config import PermitConfig, CostConfig, CoachConfig

# Realistic config: smart verbosity, $0.50 budget, opus model
config = PermitConfig(
    verbosity="smart",
    show_diagram=True,
    show_history=True,
    cost=CostConfig(
        enabled=True, model="opus", budget_usd=0.50,
        show_per_operation=True, show_session_total=True, show_tips=True,
    ),
    coach=CoachConfig(enabled=True, max_tips_per_box=2),
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
COST_PY = os.path.join(PROJECT_ROOT, "core", "cost.py")

# A realistic 6-step coding session
STEPS = [
    # (label, tool_name, tool_input, snapshot_saved)
    ("$ ls -la",
     "Bash", {"command": "ls -la"}, False),

    ("$ read core/cost.py",
     "Read", {"file_path": COST_PY}, False),

    ("# Claude edits core/cost.py (snapshot auto-saved)",
     "Edit", {"file_path": COST_PY, "old_string": "return 0", "new_string": "return 1"}, True),

    ("$ pytest                                  # full test suite after a small edit",
     "Bash", {"command": "pytest"}, False),

    ("$ rm -rf dist && npm run build            # chained destructive",
     "Bash", {"command": "rm -rf dist && npm run build"}, False),

    ("$ export ANTHROPIC_MODEL=claude-opus-4   # obsolete pattern",
     "Bash", {"command": "export ANTHROPIC_MODEL=claude-opus-4"}, False),
]


def _run_step(tool_name, tool_input, snapshot_saved, history, session_cost):
    analysis = analyze_tool(tool_name, tool_input)
    if analysis is None:
        return None, session_cost

    file_path = tool_input.get("file_path")
    cost = estimate_cost(tool_name, tool_input, config.cost.model)
    session_cost += cost.cost_usd

    workflow = detect_workflow(history, tool_name, analysis.title, file_path)
    heat = detect_file_heat(history, file_path) if file_path else 0

    coaching = []
    if analysis.risk in ("caution", "danger"):
        coaching = detect_patterns(
            tool_name, tool_input, history,
            config.cost.model, PROJECT_ROOT,
            max_tips=2,
        )

    hints = detect_hints(tool_name, tool_input, history, snapshot_saved, PROJECT_ROOT)

    chain_text = ""
    if len(history) >= 2:
        chain_text = format_chain(history[-3:], analysis.title)

    if config.verbosity == "smart" and analysis.risk == "safe":
        message = format_compact(analysis, workflow=workflow, cost=cost, hints=hints)
    else:
        message = format_explanation(
            analysis,
            related_chain=chain_text if config.show_diagram and len(history) >= 2 else "",
            workflow=workflow,
            file_heat=heat,
            verbosity="normal",
            cost=cost,
            session_cost_usd=session_cost,
            snapshot_saved=snapshot_saved,
            budget_usd=config.cost.budget_usd,
            coaching=coaching,
            hints=hints,
        )

    history.append({
        "tool_name": tool_name,
        "summary": analysis.title,
        "file_path": file_path,
        "risk": analysis.risk,
        "cost_estimate_usd": cost.cost_usd,
    })

    return message, session_cost


def main():
    print(f"\n  permit v4.2 — smarter than a rubber duck")
    print(f"  verbosity=smart  model=opus  budget=$0.50\n")

    history = []
    session_cost = 0.0

    for label, tool_name, tool_input, snapshot_saved in STEPS:
        print(f"  \033[2m{label}\033[0m")
        message, session_cost = _run_step(
            tool_name, tool_input, snapshot_saved, history, session_cost
        )
        if message:
            print(message)
        print()

    print(f"  Session total: ~${session_cost:.3f} estimated  |  "
          f"budget: ${config.cost.budget_usd:.2f}")
    print(f"  Run: python3 demo.py  |  Install: bash install.sh\n")


if __name__ == "__main__":
    main()
