"""Session report generator."""

import os
import re
from collections import Counter
from core.cost import format_cost
from core.coach import get_learning_stats

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_BOX_WIDTH = 80
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def _pad(s: str, width: int) -> str:
    vl = _vlen(s)
    if vl > width:
        s = s[:width - 3] + "..."
        vl = _vlen(s)
    return s + " " * (width - vl)


def _row(content: str) -> str:
    inner_w = _BOX_WIDTH - 4
    padded = _pad(content, inner_w)
    return f"| {padded}{_RESET} |"


def _section(title: str) -> str:
    return _row(f"{_BOLD}{title}{_RESET}")


def _blank() -> str:
    return _row("")


def generate_report(history: list) -> str:
    if not history:
        return "No session history found. permit starts tracking once Claude makes tool calls."

    inner_w = _BOX_WIDTH - 4
    top = f"+-permit-summary-{'-' * (inner_w - 13)}+"
    bottom = f"+{'-' * (inner_w + 2)}+"

    lines = ["", top]

    lines.append(_row(f"{_BOLD}SESSION REPORT{_RESET}"))
    lines.append(_blank())

    # --- Cost ---
    total_cost = sum(e.get("cost_estimate_usd", 0.0) for e in history)
    lines.append(_section("Cost"))

    cost_color = _GREEN if total_cost < 1.0 else _YELLOW if total_cost < 5.0 else _RED
    lines.append(_row(f"  Estimated total:  {cost_color}{format_cost(total_cost)}{_RESET}"))

    # Most expensive operation
    most_exp = max(history, key=lambda e: e.get("cost_estimate_usd", 0.0), default=None)
    if most_exp and most_exp.get("cost_estimate_usd", 0) > 0:
        exp_cost = format_cost(most_exp["cost_estimate_usd"])
        exp_summary = most_exp.get("summary", "unknown")[:35]
        lines.append(_row(f"  Most expensive:   {exp_summary} ({exp_cost})"))

    lines.append(_row(f"  {_DIM}Note: actual cost is higher due to context replay{_RESET}"))
    lines.append(_blank())

    # --- Operations ---
    total_ops = len(history)
    risk_counts = Counter(e.get("risk", "safe") for e in history)
    safe_n = risk_counts.get("safe", 0)
    caution_n = risk_counts.get("caution", 0)
    danger_n = risk_counts.get("danger", 0)

    lines.append(_section(f"Operations ({total_ops} total)"))
    lines.append(_row(
        f"  {_GREEN}Safe: {safe_n}{_RESET}   "
        f"{_YELLOW}Caution: {caution_n}{_RESET}   "
        f"{_RED}Danger: {danger_n}{_RESET}"
    ))
    lines.append(_blank())

    # --- Files touched ---
    file_events = [e for e in history if e.get("file_path")]
    if file_events:
        file_counts = Counter(e["file_path"] for e in file_events)
        top_files = file_counts.most_common(5)
        lines.append(_section("Files touched"))
        for path, count in top_files:
            short = _shorten(path)
            heat = f"{count}x" if count > 1 else "1x"
            lines.append(_row(f"  {short}  -- {heat}"))
        lines.append(_blank())

    # --- Snapshots ---
    snapshots = [e for e in history if e.get("snapshot_id")]
    if snapshots:
        lines.append(_section("Snapshots"))
        lines.append(_row(f"  {len(snapshots)} snapshot(s) saved"))
        lines.append(_row(f"  {_DIM}Use /permit-rollback to restore any file{_RESET}"))
        lines.append(_blank())

    # --- Learning ---
    learning = get_learning_stats()
    session_patterns = set()
    for e in history:
        # We don't store pattern IDs in events currently, but we can check learning file
        pass

    if learning:
        lines.append(_section("Learning trajectory"))
        for pid, entry in sorted(learning.items(), key=lambda x: -x[1].get("count", 0))[:4]:
            count = entry.get("count", 0)
            sessions = entry.get("sessions", 1)
            label = pid.replace("_", " ")
            if count >= 5:
                indicator = f"{_RED}flagged {count}x -- fix this{_RESET}"
            elif count >= 2:
                indicator = f"{_YELLOW}flagged {count}x across {sessions} session(s){_RESET}"
            else:
                indicator = f"{_GREEN}flagged {count}x{_RESET}"
            lines.append(_row(f"  {label}: {indicator}"))
        lines.append(_blank())

    lines.append(bottom)
    return "\n".join(lines)


def _shorten(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    parts = path.split("/")
    if len(parts) > 4:
        return parts[0] + "/.../" + "/".join(parts[-2:])
    return path
