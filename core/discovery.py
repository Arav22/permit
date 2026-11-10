"""Command discovery hints — proactively surfaces Claude Code commands.

Different from coach (which corrects mistakes), hints tell users about
relevant commands they may not know exist. Max 1 per box, suppressed
after 3 appearances so they never become noise.

Catalog is loaded from core/hints_catalog.json (bundled) and merged
with ~/.claude/permit-hints.json (user overrides). Run /permit update
to fetch the latest catalog from GitHub.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

from core.coach import _load_learning, _save_learning, _has_claude_md
from core.project_tracker import load_project_data
from core.tracker import get_session_cost


@dataclass
class Hint:
    hint_id: str
    one_liner: str
    is_obsolete: bool = False


_MAX_APPEARANCES = 3
_BUNDLED_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "hints_catalog.json")
_USER_CATALOG_PATH = os.path.expanduser("~/.claude/permit-hints.json")


def _load_catalog() -> dict:
    """Load bundled catalog + user overrides, merged by ID."""
    catalog = {"hints": [], "obsolete_patterns": []}

    for path in [_BUNDLED_CATALOG_PATH, _USER_CATALOG_PATH]:
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        # Merge hints: user entries override bundled ones by ID
        existing_ids = {h["id"] for h in catalog["hints"]}
        for h in data.get("hints", []):
            if h["id"] in existing_ids:
                catalog["hints"] = [
                    (h if entry["id"] == h["id"] else entry)
                    for entry in catalog["hints"]
                ]
            else:
                catalog["hints"].append(h)

        # Same for obsolete patterns
        existing_obs_ids = {p["id"] for p in catalog["obsolete_patterns"]}
        for p in data.get("obsolete_patterns", []):
            if p["id"] not in existing_obs_ids:
                catalog["obsolete_patterns"].append(p)

    return catalog


def _hint_seen_count(hint_id: str) -> int:
    data = _load_learning()
    return data.get(hint_id, {}).get("count", 0)


def _record_hint(hint_id: str):
    data = _load_learning()
    entry = data.get(hint_id, {"count": 0, "last_seen": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_seen"] = time.time()
    data[hint_id] = entry
    _save_learning(data)


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
    n = len(history)
    catalog = _load_catalog()
    hint_map = {h["id"]: h["one_liner"] for h in catalog.get("hints", [])}

    candidates: list[tuple[str, bool]] = []  # (id, is_obsolete)

    # --- Standard discovery hints ---

    # hint_resume: very first op of a fresh session
    if n == 0:
        candidates.append(("hint_resume", False))

    # hint_model: shown early when model hasn't been mentioned
    if n <= 2 and tool_name in ("Bash", "Edit", "Write", "Read"):
        candidates.append(("hint_model", False))

    # hint_rollback: fires once after first snapshot is saved
    if snapshot_saved:
        candidates.append(("hint_rollback", False))

    # hint_compact: session growing (15-50, before coach context_bloat at 50)
    if 15 <= n <= 50:
        candidates.append(("hint_compact", False))

    # hint_init: early session, no CLAUDE.md
    if 1 <= n <= 5 and not _has_claude_md(project_root):
        candidates.append(("hint_init", False))

    # hint_clear: session > 30 and tool type changed
    if n > 30 and _last_tool(history) != tool_name:
        candidates.append(("hint_clear", False))

    # hint_project_report: project has multiple session dates
    try:
        pdata = load_project_data(project_root)
        dates = {s.get("date") for s in pdata.get("sessions", []) if s.get("date")}
        if len(dates) >= 2:
            candidates.append(("hint_project_report", False))
    except Exception:
        pass

    # hint_add_dir: Read on a path outside cwd
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        cwd = os.getcwd()
        if path and not path.startswith(cwd) and not path.startswith("~"):
            candidates.append(("hint_add_dir", False))

    # hint_bug: bash command suggests debugging
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if any(w in cmd for w in ("--fix", "--repair", "debug", "error")):
            candidates.append(("hint_bug", False))

    # hint_config: session cost growing
    if get_session_cost() > 0.05:
        candidates.append(("hint_config", False))

    # --- Obsolescence detection (catalog-driven) ---
    obs_patterns = catalog.get("obsolete_patterns", [])
    for obs in obs_patterns:
        if obs.get("detect_in") != tool_name:
            continue
        target = tool_input.get("command", tool_input.get("file_path", ""))
        try:
            if re.search(obs["pattern"], target or ""):
                obs_id = obs["id"]
                # Obsolete hints go first — they're more urgent
                candidates.insert(0, (obs_id, True))
                # Register the one_liner for this obs entry
                hint_map[obs_id] = f"OBS: {obs['message']} -- use: {obs['newer_command']}"
                break
        except re.error:
            pass

    # Pick first candidate not yet suppressed
    for hid, is_obs in candidates:
        if _hint_seen_count(hid) < _MAX_APPEARANCES and hid in hint_map:
            _record_hint(hid)
            return [Hint(hint_id=hid, one_liner=hint_map[hid], is_obsolete=is_obs)]

    return []
