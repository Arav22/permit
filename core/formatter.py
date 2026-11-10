"""Formats analysis results into a box display.

All box content is pure ASCII — no emoji, no Unicode arrows, no em dashes.
This guarantees every character is exactly 1 terminal column, making
right-border alignment correct on every terminal and font.
"""

import re
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
_BOX_WIDTH = 68


def _vlen(s: str) -> int:
    """Visible length after stripping ANSI. ASCII-only content assumed."""
    return len(_ANSI_RE.sub("", s))


def _truncate(s: str, max_w: int) -> str:
    """Truncate to max visible width, preserving ANSI codes."""
    visible = 0
    result = []
    i = 0
    while i < len(s):
        m = _ANSI_RE.match(s, i)
        if m:
            result.append(m.group())
            i = m.end()
            continue
        if visible >= max_w - 3:
            result.append("...")
            break
        result.append(s[i])
        visible += 1
        i += 1
    return "".join(result)


def _pad(s: str, width: int) -> str:
    """Pad a line with spaces to exact visible width."""
    vl = _vlen(s)
    if vl > width:
        s = _truncate(s, width)
        vl = _vlen(s)
    return s + " " * (width - vl)


def _ascii(s: str) -> str:
    """Strip all non-ASCII characters from a string."""
    return "".join(c for c in s if ord(c) < 128)


def format_explanation(
    analysis: Analysis,
    related_chain: str = "",
    workflow: Optional[WorkflowMatch] = None,
    file_heat: int = 0,
    verbosity: str = "normal",
) -> str:
    color = _RISK_COLORS.get(analysis.risk, "")
    label = _RISK_LABELS.get(analysis.risk, "UNKNOWN")
    title = _ascii(analysis.title).strip()

    rows = []

    rows.append(f"{color}{_BOLD}{label}{_RESET} {title}")
    rows.append(f"  {_ascii(analysis.explanation).strip()}")

    if analysis.stages and verbosity != "minimal":
        rows.append("")
        for stage in analysis.stages:
            rows.append(f"  -> {_ascii(stage).strip()}")

    if analysis.warnings:
        rows.append("")
        for w in analysis.warnings:
            rows.append(f"{_RED}!! {_ascii(w).strip()}{_RESET}")

    if verbosity != "minimal":
        blast = _BLAST_LABELS.get(analysis.blast_radius, "")
        scope_line = _ascii(analysis.scope).strip()
        if blast:
            scope_line += f" [{blast}]"
        rows.append("")
        rows.append(f"{_DIM}Scope: {scope_line}{_RESET}")

    if file_heat > 1 and verbosity != "minimal":
        rows.append(f"{_DIM}Touched {file_heat}x this session{_RESET}")

    if workflow and verbosity != "minimal":
        wf_label = _ascii(workflow.label).strip()
        step = f"step {workflow.stage + 1}/{workflow.total}"
        rows.append(f"{_DIM}Flow: {wf_label} ({step}){_RESET}")

    if related_chain and verbosity != "minimal":
        chain_lines = _ascii(related_chain).strip().split("\n")
        if len(chain_lines) > 1:
            rows.append("")
            rows.append(f"{_DIM}Recent:{_RESET}")
            for cl in chain_lines:
                rows.append(f"{_DIM}  {cl.strip()}{_RESET}")

    return _build_box(rows)


def format_compact(analysis: Analysis, workflow: Optional[WorkflowMatch] = None) -> str:
    color = _RISK_COLORS.get(analysis.risk, "")
    label = _RISK_LABELS.get(analysis.risk, "?")
    explanation = _ascii(analysis.explanation).strip()
    line = f"{color}{label}{_RESET}: {explanation}"
    if workflow:
        wf_label = _ascii(workflow.label).strip()
        line += f" {_DIM}[{wf_label}]{_RESET}"
    return line


def _build_box(rows: list[str]) -> str:
    """Build a proper 4-sided box. All content is ASCII so len() == columns."""
    inner_w = _BOX_WIDTH - 4  # "| " content " |"

    top = f"+-permit-{'-' * (inner_w - 6)}+"
    bottom = f"+{'-' * (inner_w + 2)}+"

    lines = ["", top]
    for row in rows:
        padded = _pad(row, inner_w)
        lines.append(f"| {padded}{_RESET} |")
    lines.append(bottom)

    return "\n".join(lines)
