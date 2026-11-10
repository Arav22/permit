"""Cross-session project report with ASCII bar charts and optional HTML."""

import os
import re
import time
from collections import Counter
from datetime import datetime

from core.cost import format_cost
from core.project_tracker import load_project_data

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_BOX_WIDTH = 68
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
        s = _ANSI_RE.sub("", s)[:width - 3] + "..."
        vl = len(s)
    return s + " " * (width - vl)


def _row(content: str) -> str:
    inner_w = _BOX_WIDTH - 4
    padded = _pad(content, inner_w)
    return f"| {padded}{_RESET} |"


def _section(title: str) -> str:
    return _row(f"{_BOLD}{title}{_RESET}")


def _blank() -> str:
    return _row("")


def _ascii_bar(value: float, max_val: float, width: int = 20) -> str:
    if max_val <= 0:
        filled = 0
    else:
        filled = int((value / max_val) * width)
    return "=" * filled + "-" * (width - filled)


def _cost_color(cost_usd: float) -> str:
    if cost_usd >= 5.0:
        return _RED
    if cost_usd >= 1.0:
        return _YELLOW
    return _GREEN


def generate_project_report(view: str = "summary", project_root: str = "") -> str:
    data = load_project_data(project_root)
    sessions = data.get("sessions", [])

    if not sessions:
        return "No project history yet. permit starts tracking once Claude makes tool calls."

    inner_w = _BOX_WIDTH - 4
    top = f"+-permit-project-{'-' * (inner_w - 14)}+"
    bottom = f"+{'-' * (inner_w + 2)}+"
    lines = ["", top]
    lines.append(_row(f"{_BOLD}PROJECT REPORT{_RESET}"))
    lines.append(_blank())

    total_cost = data.get("total_cost_usd", 0.0)
    total_ops = data.get("total_operations", 0)
    total_sess = data.get("total_sessions", len(sessions))
    proj_name = data.get("project", os.path.basename(os.getcwd()))

    cost_color = _cost_color(total_cost)
    lines.append(_row(f"  Project: {proj_name}"))
    lines.append(_row(
        f"  Total spend: {cost_color}{format_cost(total_cost)}{_RESET}"
        f"  across {total_sess} session(s)  {_DIM}({total_ops} ops){_RESET}"
    ))
    lines.append(_row(f"  {_DIM}Note: actual cost higher due to context replay{_RESET}"))
    lines.append(_blank())

    if view in ("summary", "sessions"):
        # --- Session cost bar chart ---
        lines.append(_section("Session costs"))
        recent = sessions[-8:]  # last 8 sessions
        max_cost = max((s.get("cost_usd", 0) for s in recent), default=0.01)
        today = datetime.now().strftime("%Y-%m-%d")
        for s in recent:
            date = s.get("date", "?")
            cost = s.get("cost_usd", 0.0)
            bar = _ascii_bar(cost, max_cost, width=22)
            label = "today" if date == today else "     "
            cc = _cost_color(cost)
            lines.append(_row(
                f"  {_DIM}{date}{_RESET}  [{bar}]  {cc}{format_cost(cost)}{_RESET}  {_DIM}{label}{_RESET}"
            ))
        lines.append(_blank())

    if view in ("summary", "tools"):
        # --- Tool breakdown ---
        all_tool_counts: Counter = Counter()
        for s in sessions:
            for tool, count in s.get("tool_counts", {}).items():
                all_tool_counts[tool] += count
        if all_tool_counts:
            lines.append(_section("Top tools used"))
            max_count = max(all_tool_counts.values(), default=1)
            for tool, count in all_tool_counts.most_common(6):
                bar = _ascii_bar(count, max_count, width=18)
                lines.append(_row(f"  {tool:<10} [{bar}] {count}"))
            lines.append(_blank())

    if view in ("summary", "files"):
        # --- Hottest files ---
        file_sessions: dict = {}
        for s in sessions:
            for fp in s.get("files_changed", []):
                if fp not in file_sessions:
                    file_sessions[fp] = {"count": 0, "sessions": 0}
                file_sessions[fp]["count"] += 1
                file_sessions[fp]["sessions"] += 1

        if file_sessions:
            top = sorted(file_sessions.items(), key=lambda x: -x[1]["count"])[:5]
            lines.append(_section("Hottest files"))
            for fp, info in top:
                short = _shorten(fp)
                lines.append(_row(
                    f"  {short}  {_DIM}touched {info['count']}x  "
                    f"across {info['sessions']} session(s){_RESET}"
                ))
            lines.append(_blank())

    if view in ("summary", "coach"):
        # --- Coach trends ---
        all_patterns: Counter = Counter()
        for s in sessions:
            for pid, cnt in s.get("patterns_detected", {}).items():
                all_patterns[pid] += cnt

        if all_patterns:
            lines.append(_section("Coach trends"))
            # Compare last 2 sessions to show improving/regressing
            prev_patterns: Counter = Counter()
            curr_patterns: Counter = Counter()
            if len(sessions) >= 2:
                for pid, cnt in sessions[-2].get("patterns_detected", {}).items():
                    prev_patterns[pid] += cnt
            if sessions:
                for pid, cnt in sessions[-1].get("patterns_detected", {}).items():
                    curr_patterns[pid] += cnt

            for pid, total in all_patterns.most_common(6):
                label = pid.replace("_", " ")
                curr = curr_patterns.get(pid, 0)
                prev = prev_patterns.get(pid, 0)
                if curr < prev:
                    trend = f"{_GREEN}[IMPROVING]{_RESET}"
                elif curr > prev and prev > 0:
                    trend = f"{_RED}[GETTING WORSE]{_RESET}"
                else:
                    trend = f"{_DIM}[STEADY]{_RESET}"
                lines.append(_row(f"  {label:<28} {total}x total  {trend}"))
            lines.append(_blank())

    lines.append(bottom)
    return "\n".join(lines)


def generate_html_report(project_root: str = "") -> str:
    """Generate a self-contained HTML report. Save to .permit/report.html."""
    data = load_project_data(project_root)
    sessions = data.get("sessions", [])
    proj_name = data.get("project", "project")
    total_cost = data.get("total_cost_usd", 0.0)
    total_ops = data.get("total_operations", 0)

    session_rows = ""
    for s in sessions[-20:]:
        cost = s.get("cost_usd", 0.0)
        pct = min(100, int((cost / max(total_cost, 0.01)) * 100))
        ops = s.get("operation_count", 0)
        date = s.get("date", "?")
        model = s.get("model", "opus")
        session_rows += f"""
        <tr>
            <td>{date}</td>
            <td>${cost:.4f}</td>
            <td><div class="bar" style="width:{pct}%"></div></td>
            <td>{ops}</td>
            <td>{model}</td>
        </tr>"""

    all_patterns: Counter = Counter()
    for s in sessions:
        for pid, cnt in s.get("patterns_detected", {}).items():
            all_patterns[pid] += cnt

    pattern_rows = ""
    for pid, cnt in all_patterns.most_common(10):
        pattern_rows += f"<tr><td>{pid.replace('_',' ')}</td><td>{cnt}</td></tr>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>permit — {proj_name} report</title>
<style>
  body {{ font-family: monospace; background: #1a1a1a; color: #d4d4d4; padding: 2rem; }}
  h1 {{ color: #4ec9b0; }} h2 {{ color: #9cdcfe; border-bottom: 1px solid #333; padding-bottom: .5rem; }}
  .stat {{ display: inline-block; background: #252525; border-radius: 6px; padding: 1rem 2rem; margin: .5rem; }}
  .stat .num {{ font-size: 2rem; color: #4ec9b0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th {{ background: #252525; padding: .5rem 1rem; text-align: left; color: #9cdcfe; }}
  td {{ padding: .4rem 1rem; border-bottom: 1px solid #2a2a2a; }}
  .bar {{ height: 12px; background: #4ec9b0; border-radius: 2px; min-width: 2px; }}
  tr:hover td {{ background: #252525; }}
</style>
</head>
<body>
<h1>permit — {proj_name}</h1>
<div>
  <div class="stat"><div class="num">${total_cost:.2f}</div><div>total spend</div></div>
  <div class="stat"><div class="num">{len(sessions)}</div><div>sessions</div></div>
  <div class="stat"><div class="num">{total_ops}</div><div>operations</div></div>
</div>
<h2>Sessions</h2>
<table>
  <tr><th>Date</th><th>Cost</th><th>Bar</th><th>Ops</th><th>Model</th></tr>
  {session_rows}
</table>
<h2>Anti-patterns detected</h2>
<table>
  <tr><th>Pattern</th><th>Count</th></tr>
  {pattern_rows}
</table>
<p style="color:#555;font-size:.8rem">Generated by permit. Actual cost higher due to context replay.</p>
</body>
</html>"""


def save_html_report(project_root: str = "") -> str:
    """Save HTML report to .permit/report.html and return the path."""
    root = project_root or os.getcwd()
    out_path = os.path.join(root, ".permit", "report.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    html = generate_html_report(project_root)
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


def _shorten(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    parts = path.split("/")
    if len(parts) > 4:
        return parts[0] + "/.../" + "/".join(parts[-2:])
    return path
