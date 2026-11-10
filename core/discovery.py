"""Command discovery hints — proactively surfaces Claude Code commands.

Different from coach (which corrects mistakes), hints tell users about
relevant commands they may not know exist. Max 1 per box, suppressed
after 3 appearances so they never become noise.
"""

import os
from dataclasses import dataclass

from core.coach import _load_learning, _save_learning, _has_claude_md
from core.project_tracker import load_project_data
from core.tracker import get_session_cost


@dataclass
class Hint:
    hint_id: str
    one_liner: str


_HINTS = [
    # ID, trigger description (handled in detect_hints), one-liner
    ("hint_resume",        "/resume -- pick up a previous session where you left off"),
    ("hint_model",         "/model sonnet -- switch model for cheaper routine work"),
    ("hint_rollback",      "/permit-rollback -- undo any file change with fuzzy matching"),
    ("hint_compact",       "/compact -- compress context without losing work"),
    ("hint_init",          "/init -- auto-generate CLAUDE.md from your project"),
    ("hint_clear",         "/clear -- fresh context when moving to a new task"),
    ("hint_project_report","/permit project -- see costs and patterns across all sessions"),
    ("hint_add_dir",       "/add-dir -- add another project directory to context"),
    ("hint_bug",           "/bug -- report this to Anthropic with full session context"),
    ("hint_config",        "/permit config -- view and change permit settings"),
]

_HINT_MAP = {hid: line for hid, line in _HINTS}

_MAX_APPEARANCES = 3


def _hint_seen_count(hint_id: str) -> int:
    data = _load_learning()
    return data.get(hint_id, {}).get("count", 0)


def _record_hint(hint_id: str):
    import time
    data = _load_learning()
    entry = data.get(hint_id, {"count": 0, "last_seen": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_seen"] = time.time()
    data[hint_id] = entry
    _save_learning(data)


def _session_len(history: list) -> int:
    return len(history)


def _last_tool(history: list) -> str:
    if not history:
        return ""
    return history[-1].get("tool_name", "")


def detect_hints(
    tool_name: str,
    tool_input: dict,
    history: list,
    snapshot_saved: bool,
    project_root: str,
) -> list[Hint]:
    n = _session_len(history)
    candidates = []

    # hint_resume: very first op of a fresh session (n==0, nothing in history yet)
    if n == 0:
        candidates.append("hint_resume")

    # hint_model: shown early in session when model hasn't been mentioned
    if n <= 2 and tool_name in ("Bash", "Edit", "Write", "Read"):
        candidates.append("hint_model")

    # hint_rollback: fires once after first snapshot is saved
    if snapshot_saved:
        candidates.append("hint_rollback")

    # hint_compact: session growing (15-50 range, before coach context_bloat fires at 50)
    if 15 <= n <= 50:
        candidates.append("hint_compact")

    # hint_init: early session, no CLAUDE.md (lighter than no_claude_md coach)
    if 1 <= n <= 5 and not _has_claude_md(project_root):
        candidates.append("hint_init")

    # hint_clear: session > 30 events and tool type changed (switching context)
    if n > 30:
        last = _last_tool(history)
        if last and last != tool_name:
            candidates.append("hint_clear")

    # hint_project_report: project has multiple session dates → show cross-session report
    try:
        pdata = load_project_data(project_root)
        dates = {s.get("date") for s in pdata.get("sessions", []) if s.get("date")}
        if len(dates) >= 2:
            candidates.append("hint_project_report")
    except Exception:
        pass

    # hint_add_dir: Read on a path clearly outside cwd
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        cwd = os.getcwd()
        if path and not path.startswith(cwd) and not path.startswith("~"):
            candidates.append("hint_add_dir")

    # hint_bug: bash command summary suggests an error (heuristic)
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if any(w in cmd for w in ("--fix", "--repair", "debug", "error")):
            candidates.append("hint_bug")

    # hint_config: session has accumulated some cost
    if get_session_cost() > 0.05:
        candidates.append("hint_config")

    # Pick first candidate not yet suppressed
    result = []
    for hid in candidates:
        if _hint_seen_count(hid) < _MAX_APPEARANCES and hid in _HINT_MAP:
            _record_hint(hid)
            result.append(Hint(hint_id=hid, one_liner=_HINT_MAP[hid]))
            break  # max 1 hint per box

    return result
