"""Formats analysis results into a box display."""

import re
import unicodedata
from core.analyzer import Analysis
from core.patterns import WorkflowMatch
from typing import Optional

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"

_RISK_COLORS = {"safe": _GREEN, "caution": _YELLOW, "danger": _RED}
_RISK_LABELS = {"safe": "SAFE", "caution": "CAUTION", "danger": "DANGER"}
_BLAST_LABELS = {
    "project": "Project files",
    "system": "System-wide",
    "remote": "Remote / visible to others",
}

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_BOX_WIDTH = 62
_FE0F = "️"


def _char_width(ch: str) -> int:
    """Terminal column width of a single character."""
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    return 1


def _vlen(s: str) -> int:
    """Visible terminal column width, ignoring ANSI escapes."""
    clean = _ANSI_RE.sub("", s)
    width = 0
    prev_w = 0
    for ch in clean:
        if ch == _FE0F:
            if prev_w == 1:
                width += 1
                prev_w = 2
            continue
        cw = _char_width(ch)
        width += cw
        prev_w = cw
    return width


def _truncate(s: str, max_w: int) -> str:
    """Truncate to max visible width, preserving ANSI codes."""
    visible = 0
    result = []
    prev_w = 0
    i = 0
    while i < len(s):
        m = _ANSI_RE.match(s, i)
        if m:
            result.append(m.group())
            i = m.end()
            continue
        if s[i] == _FE0F:
            extra = 1 if prev_w == 1 else 0
            if visible + extra > max_w - 1:
                result.append("...")
                break
            result.append(s[i])
            visible += extra
            if extra:
                prev_w = 2
            i += 1
            continue
        cw = _char_width(s[i])
        if visible + cw > max_w - 1:
            result.append("...")
            break
        result.append(s[i])
        visible += cw
        prev_w = cw
        i += 1
    return "".join(result)


def _pad_line(s: str, width: int) -> str:
    """Pad a line with spaces to exact visible terminal width."""
    vl = _vlen(s)
    if vl > width:
        s = _truncate(s, width)
        vl = _vlen(s)
    return s + " " * (width - vl)


def format_explanation(
    analysis: Analysis,
    related_chain: str = "",
    workflow: Optional[WorkflowMatch] = None,
    file_heat: int = 0,
    verbosity: str = "normal",
) -> str:
    color = _RISK_COLORS.get(analysis.risk, "")
    label = _RISK_LABELS.get(analysis.risk, "UNKNOWN")

    rows = []

    # Line 1: risk badge + what command/action
    rows.append(f"{analysis.icon}  {color}{_BOLD}{label}{_RESET} -- {analysis.title}")

    # Line 2: plain-English explanation
    rows.append(f"   {analysis.explanation}")

    # Stages (pipe/chain breakdown)
    if analysis.stages and verbosity != "minimal":
        rows.append("")
        for stage in analysis.stages:
            rows.append(f"  -> {stage}")

    # Warnings first — these are the most important
    if analysis.warnings:
        rows.append("")
        for w in analysis.warnings:
            rows.append(f"{_RED}!! {w}{_RESET}")

    # Scope
    if verbosity != "minimal":
        blast = _BLAST_LABELS.get(analysis.blast_radius, "")
        scope_line = analysis.scope
        if blast:
            scope_line += f" [{blast}]"
        rows.append("")
        rows.append(f"{_DIM}Scope: {scope_line}{_RESET}")

    if file_heat > 1 and verbosity != "minimal":
        rows.append(f"{_DIM}Touched {file_heat}x this session{_RESET}")

    # Workflow pattern
    if workflow and verbosity != "minimal":
        step = f"step {workflow.stage + 1}/{workflow.total}"
        rows.append(f"{_DIM}Flow: {workflow.label} ({step}){_RESET}")

    # Chain — only show if there are meaningful recent entries
    if related_chain and verbosity != "minimal":
        chain_lines = related_chain.strip().split("\n")
        if len(chain_lines) > 1:
            rows.append("")
            rows.append(f"{_DIM}Recent:{_RESET}")
            for chain_line in chain_lines:
                rows.append(f"{_DIM}  {chain_line}{_RESET}")

    return _build_box(rows)


def format_compact(analysis: Analysis, workflow: Optional[WorkflowMatch] = None) -> str:
    color = _RISK_COLORS.get(analysis.risk, "")
    label = _RISK_LABELS.get(analysis.risk, "?")
    line = f"{analysis.icon} {color}{label}{_RESET}: {analysis.explanation}"
    if workflow:
        line += f" {_DIM}[{workflow.label}]{_RESET}"
    return line


def _build_box(rows: list[str]) -> str:
    """Build a proper 4-sided box. Content padded to fixed width."""
    inner_w = _BOX_WIDTH - 4  # "| " content " |"

    top = f"+-permit-{'-' * (inner_w - 6)}+"
    bottom = f"+{'-' * (inner_w + 2)}+"

    lines = ["", top]
    for row in rows:
        padded = _pad_line(row, inner_w)
        lines.append(f"| {padded}{_RESET} |")
    lines.append(bottom)

    return "\n".join(lines)
