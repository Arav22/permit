"""Formats analysis results into a box display.

All box content is pure ASCII — no emoji, no Unicode arrows, no em dashes.
This guarantees every character is exactly 1 terminal column, making
right-border alignment correct on every terminal and font.
"""

import re
from core.analyzer import Analysis
from core.coach import Coaching
from core.cost import CostEstimate, format_cost, format_tokens, check_budget, format_budget_bar
from core.discovery import Hint
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
_BOX_WIDTH = 80


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


def _wrap(text: str, width: int, indent: str = "", cont_indent: str = "") -> list[str]:
    """Word-wrap text to width. First line gets `indent`, continuations get `cont_indent`."""
    if not cont_indent:
        cont_indent = " " * len(indent)
    words = _ascii(text).strip().split()
    lines: list[str] = []
    current = indent
    first = True
    for word in words:
        prefix = indent if first else cont_indent
        candidate = (current + " " + word) if current.strip() else prefix + word
        if len(candidate) <= width:
            current = candidate
        else:
            if current.strip():
                lines.append(current)
            current = cont_indent + word
            first = False
    if current.strip():
        lines.append(current)
    return lines or [indent]


def _cost_color(cost_usd: float) -> str:
    if cost_usd >= 0.10:
        return _RED
    if cost_usd >= 0.01:
        return _YELLOW
    return _GREEN


def _budget_color(status: str) -> str:
    if status == "danger":
        return _RED
    if status == "caution":
        return _YELLOW
    return _GREEN


def format_explanation(
    analysis: Analysis,
    related_chain: str = "",
    workflow: Optional[WorkflowMatch] = None,
    file_heat: int = 0,
    verbosity: str = "normal",
    cost: Optional[CostEstimate] = None,
    session_cost_usd: float = 0.0,
    snapshot_saved: bool = False,
    budget_usd: float = 0.0,
    coaching: Optional[list[Coaching]] = None,
    hints: Optional[list[Hint]] = None,
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

    # Intent line — why Claude is doing this in context
    if workflow and workflow.confidence >= 0.5 and verbosity != "minimal":
        rows.append(f"{_DIM}Why: {_ascii(workflow.description).strip()}{_RESET}")

    if analysis.warnings:
        rows.append("")
        for w in analysis.warnings:
            rows.append(f"{_RED}!! {_ascii(w).strip()}{_RESET}")

    if verbosity != "minimal":
        blast = _BLAST_LABELS.get(analysis.blast_radius, "")
        scope_line = _ascii(analysis.scope).strip()
        if blast:
            scope_line += f" [{blast}]"
        if snapshot_saved:
            scope_line += " [Snapshot saved]"
        rows.append("")
        rows.append(f"{_DIM}Scope: {scope_line}{_RESET}")

    if cost and verbosity != "minimal":
        cc = _cost_color(cost.cost_usd)
        left = f"{cc}Cost: {format_cost(cost.cost_usd)} (est. {format_tokens(cost.input_tokens + cost.output_tokens)} tokens){_RESET}"

        if budget_usd > 0 and session_cost_usd > 0:
            budget_status = check_budget(session_cost_usd, budget_usd)
            bc = _budget_color(budget_status)
            bar = _ascii(format_budget_bar(session_cost_usd, budget_usd))
            rows.append(left)
            rows.append(f"{bc}Budget: {bar}{_RESET}")
        elif session_cost_usd > 0:
            right = f"{_DIM}Session: {format_cost(session_cost_usd)}{_RESET}"
            rows.append(f"{left}  {right}")
        else:
            rows.append(left)

    if cost and cost.tips and verbosity != "minimal":
        for tip in cost.tips:
            rows.append(f"{_CYAN}TIP: {_ascii(tip).strip()}{_RESET}")

    # Discovery hints — one-liner, shown in all verbosity levels (even smart)
    if hints and verbosity != "minimal":
        h = hints[0]
        hcolor = _YELLOW if h.is_obsolete else _DIM
        rows.append(f"{hcolor}HINT: {_ascii(h.one_liner).strip()}{_RESET}")

    # Coach tips — shown in normal/detailed, never minimal/smart
    inner_w = _BOX_WIDTH - 4
    if coaching and verbosity not in ("minimal", "smart"):
        for c in coaching:
            rows.append("")
            rows.append(f"{_CYAN}COACH: {_ascii(c.title).strip()}{_RESET}")
            for line in _wrap(c.problem, inner_w, "  "):
                rows.append(line)
            for line in _wrap(c.right_way, inner_w, "  Fix: "):
                rows.append(line)
            if c.command:
                rows.append(f"  {_DIM}Command: {_ascii(c.command)}{_RESET}")

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


def format_compact(
    analysis: Analysis,
    workflow: Optional[WorkflowMatch] = None,
    cost: Optional[CostEstimate] = None,
    hints: Optional[list[Hint]] = None,
) -> str:
    color = _RISK_COLORS.get(analysis.risk, "")
    label = _RISK_LABELS.get(analysis.risk, "?")
    explanation = _ascii(analysis.explanation).strip()
    line = f"{color}{label}{_RESET}: {explanation}"
    if workflow:
        wf_label = _ascii(workflow.label).strip()
        line += f" {_DIM}[{wf_label}]{_RESET}"
    if cost:
        line += f" {_DIM}{format_cost(cost.cost_usd)}{_RESET}"
    if hints:
        h = hints[0]
        hcolor = _YELLOW if h.is_obsolete else _DIM
        line += f"  {hcolor}| HINT: {_ascii(h.one_liner).strip()}{_RESET}"
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
