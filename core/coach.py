"""Claude Code anti-pattern detection and learning trajectory."""

import json
import os
import re
import time
from dataclasses import dataclass


@dataclass
class Coaching:
    pattern_id: str
    title: str
    problem: str
    right_way: str
    command: str
    severity: str = "tip"


_LEARNING_FILE = os.path.join(os.path.expanduser("~"), ".claude", "permit-learning.json")

_PATTERNS = [
    {
        "id": "opus_for_coding",
        "title": "Using Opus for routine coding",
        "problem": "Opus costs 5x more than Sonnet with no quality difference for coding tasks",
        "right_way": "Use Sonnet for edits/bash/reads. Switch to Opus for planning and architecture only.",
        "command": "/model sonnet",
        "severity": "tip",
    },
    {
        "id": "context_bloat",
        "title": "Session context is growing large",
        "problem": "Every turn replays the full conversation -- large context = expensive turns",
        "right_way": "Use /compact to compress history. Use /clear when switching to a new task.",
        "command": "/compact",
        "severity": "warning",
    },
    {
        "id": "big_read_no_limit",
        "title": "Reading a large file without offset/limit",
        "problem": "Reading 800 lines when you need 20 wastes tokens and context space",
        "right_way": "Use offset and limit params: Read(file, offset=100, limit=50)",
        "command": "offset/limit params",
        "severity": "tip",
    },
    {
        "id": "full_test_run",
        "title": "Running full test suite for a small change",
        "problem": "Full test runs are slow and costly -- usually unnecessary for targeted changes",
        "right_way": "Run only the relevant test file: pytest tests/test_X.py",
        "command": "pytest tests/test_X.py",
        "severity": "tip",
    },
    {
        "id": "agent_overkill",
        "title": "Spawning an agent for a simple task",
        "problem": "Agent spawns start a new model context -- expensive for tasks Claude can do directly",
        "right_way": "Ask Claude directly instead of spawning a subagent",
        "command": "",
        "severity": "tip",
    },
    {
        "id": "no_claude_md",
        "title": "No CLAUDE.md found in project",
        "problem": "Without CLAUDE.md, Claude re-learns your project every session, burning context",
        "right_way": "Create CLAUDE.md with project overview, conventions, and common commands",
        "command": "/init",
        "severity": "tip",
    },
    {
        "id": "repeated_large_read",
        "title": "Reading the same large file multiple times",
        "problem": "Each read replays the file content into context -- use offset/limit or summarise once",
        "right_way": "Use offset/limit to read specific sections, or ask Claude to remember key parts",
        "command": "offset/limit params",
        "severity": "tip",
    },
]

_PATTERN_MAP = {p["id"]: p for p in _PATTERNS}


def _load_learning() -> dict:
    try:
        with open(_LEARNING_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_learning(data: dict):
    os.makedirs(os.path.dirname(_LEARNING_FILE), exist_ok=True)
    try:
        with open(_LEARNING_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def record_pattern(pattern_id: str):
    data = _load_learning()
    entry = data.get(pattern_id, {"count": 0, "sessions": 0, "last_seen": 0})
    entry["count"] = entry.get("count", 0) + 1
    entry["last_seen"] = time.time()
    data[pattern_id] = entry
    _save_learning(data)


def get_learning_stats() -> dict:
    return _load_learning()


def format_trajectory(pattern_id: str) -> str:
    data = _load_learning()
    entry = data.get(pattern_id)
    if not entry:
        return ""
    count = entry.get("count", 0)
    if count >= 5:
        return f"You've seen this tip {count} times -- fix it permanently with the command above"
    if count >= 2:
        return f"You've seen this {count} times -- getting there"
    return ""


def _has_claude_md(project_root: str) -> bool:
    for name in ("CLAUDE.md", ".claude/CLAUDE.md"):
        if os.path.exists(os.path.join(project_root, name)):
            return True
    return False


def _session_event_count(history: list) -> int:
    return len(history)


def _same_file_read_count(history: list, file_path: str) -> int:
    if not file_path:
        return 0
    return sum(
        1 for e in history
        if e.get("tool_name") == "Read" and e.get("file_path") == file_path
    )


def detect_patterns(
    tool_name: str,
    tool_input: dict,
    history: list,
    model: str,
    project_root: str,
    max_tips: int = 2,
) -> list[Coaching]:
    found = []

    # opus_for_coding: using opus for routine coding tools
    if tool_name in ("Bash", "Edit", "Write", "Read") and "opus" in model.lower():
        found.append("opus_for_coding")

    # context_bloat: session > 50 events
    if _session_event_count(history) > 50:
        found.append("context_bloat")

    # big_read_no_limit: large file read without offset/limit
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        has_limit = "limit" in tool_input or "offset" in tool_input
        if not has_limit and path:
            try:
                with open(path, "r") as _f:
                    line_count = sum(1 for _ in _f)
                if line_count > 500:
                    found.append("big_read_no_limit")
            except OSError:
                pass

    # full_test_run: running full test suite
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if re.search(r"\bpytest\b|\bnpm test\b|\bcargo test\b", cmd):
            if not re.search(r"\b-k\b|\btest_\w+\.py\b|::\w+|tests/test_", cmd):
                found.append("full_test_run")

    # agent_overkill: short/simple agent description
    if tool_name == "Agent":
        desc = tool_input.get("description", tool_input.get("prompt", ""))
        if len(desc) < 80:
            found.append("agent_overkill")

    # no_claude_md: first read/edit/write in session
    if tool_name in ("Read", "Edit", "Write") and len(history) <= 3:
        if not _has_claude_md(project_root):
            found.append("no_claude_md")

    # repeated_large_read: same file read 3+ times
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        if path and _same_file_read_count(history, path) >= 3:
            found.append("repeated_large_read")

    # Deduplicate, limit, build Coaching objects
    seen = set()
    result = []
    for pid in found:
        if pid in seen or len(result) >= max_tips:
            break
        seen.add(pid)
        p = _PATTERN_MAP.get(pid)
        if p:
            trajectory = format_trajectory(pid)
            right_way = p["right_way"]
            if trajectory:
                right_way = f"{right_way}  ({trajectory})"
            result.append(Coaching(
                pattern_id=pid,
                title=p["title"],
                problem=p["problem"],
                right_way=right_way,
                command=p["command"],
                severity=p["severity"],
            ))
            record_pattern(pid)

    return result
