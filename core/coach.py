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
    # --- Original 7 ---
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
    # --- New 8 (from Claude Code docs, DeepLearning.AI, MNC production tips) ---
    {
        "id": "write_instead_of_edit",
        "title": "Using Write on an existing file",
        "problem": "Write rewrites the entire file -- one missed line and existing code is gone",
        "right_way": "Use Edit to change specific lines. Write is for new files only.",
        "command": "Edit tool",
        "severity": "warning",
    },
    {
        "id": "no_git_commit",
        "title": "Many edits without a git checkpoint",
        "problem": "10+ file changes with no commit means no rollback point if something breaks",
        "right_way": "Commit periodically so you can git reset to a known-good state",
        "command": 'git commit -m "checkpoint"',
        "severity": "warning",
    },
    {
        "id": "edit_unread_file",
        "title": "Editing a file that wasn't read first",
        "problem": "Claude edits files it hasn't seen -- risks clobbering code outside the target area",
        "right_way": "Always Read the file before Edit/Write so Claude sees the full context",
        "command": "Read tool first",
        "severity": "warning",
    },
    {
        "id": "long_session",
        "title": "Session has grown very long (100+ events)",
        "problem": "Context replay on 100+ events is expensive -- each turn costs more than it needs to",
        "right_way": "Start a fresh session for new tasks. Use /clear between unrelated work.",
        "command": "/clear",
        "severity": "warning",
    },
    {
        "id": "missing_tests",
        "title": "Editing source code without touching tests",
        "problem": "Code changes without tests are unverified -- Claude has no feedback loop",
        "right_way": "Write or update the test file alongside every source change",
        "command": "pytest tests/test_X.py",
        "severity": "tip",
    },
    {
        "id": "webfetch_repeated",
        "title": "Fetching the same documentation site repeatedly",
        "problem": "Re-fetching the same docs wastes tokens and slows down the session",
        "right_way": "Copy key sections into CLAUDE.md so Claude always has them in context",
        "command": "CLAUDE.md",
        "severity": "tip",
    },
    {
        "id": "chained_destructive",
        "title": "Chaining rm with other commands",
        "problem": "rm && other_cmd means you can't stop between -- if rm deletes too much, it's too late",
        "right_way": "Run rm separately, verify the result, then run the next command",
        "command": "run rm separately",
        "severity": "warning",
    },
    {
        "id": "no_specific_target",
        "title": "Agent task has no specific file or function target",
        "problem": "Vague agent descriptions cause scope creep and hallucinated file paths",
        "right_way": "Name the exact file, function, or line range in the agent description",
        "command": "include file paths",
        "severity": "tip",
    },
]

_PATTERN_MAP = {p["id"]: p for p in _PATTERNS}

# Track which patterns fired in this process invocation (for sessions counter)
_this_invocation: set = set()


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
    # Increment sessions only on first occurrence per process invocation
    if pattern_id not in _this_invocation:
        entry["sessions"] = entry.get("sessions", 0) + 1
        _this_invocation.add(pattern_id)
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
    if count >= 10:
        return f"10+ occurrences. This is your top anti-pattern. One command fixes it forever:"
    if count >= 5:
        return f"Still happening after {count} times. Run the command above NOW."
    if count >= 2:
        return f"You've hit this {count} times -- here's the permanent fix:"
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


def _edits_since_last_commit(history: list) -> int:
    count = 0
    for event in reversed(history):
        if event.get("tool_name") == "Bash" and "git commit" in event.get("summary", ""):
            break
        if event.get("tool_name") in ("Edit", "Write"):
            count += 1
    return count


def _file_was_read(history: list, file_path: str) -> bool:
    if not file_path:
        return True
    return any(
        e.get("tool_name") == "Read" and e.get("file_path") == file_path
        for e in history
    )


def _is_src_file(file_path: str) -> bool:
    if not file_path:
        return False
    name = os.path.basename(file_path)
    exts = (".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java")
    return (
        any(name.endswith(e) for e in exts)
        and not name.startswith("test_")
        and ".test." not in name
        and ".spec." not in name
    )


def _has_test_write_in_session(history: list) -> bool:
    for e in history:
        if e.get("tool_name") in ("Edit", "Write"):
            name = os.path.basename(e.get("file_path", ""))
            if name.startswith("test_") or ".test." in name or ".spec." in name:
                return True
    return False


def _get_changed_src_files(history: list) -> list[str]:
    """Return source files edited this session (not test files)."""
    seen = []
    for e in history:
        if e.get("tool_name") in ("Edit", "Write"):
            fp = e.get("file_path", "")
            if fp and _is_src_file(fp) and fp not in seen:
                seen.append(fp)
    return seen


def _find_test_file(src_path: str, project_root: str) -> str:
    """Find the test file for a given source file, relative to project_root."""
    name = os.path.splitext(os.path.basename(src_path))[0]
    test_name = f"test_{name}.py"
    # Walk project looking for the test file
    for dirpath, _dirs, files in os.walk(project_root):
        if test_name in files:
            return os.path.relpath(os.path.join(dirpath, test_name), project_root)
    # Fallback: guess tests/ directory
    return os.path.join("tests", test_name)


def _smart_test_command(history: list, project_root: str) -> str:
    """Given session history, return the targeted pytest command."""
    changed = _get_changed_src_files(history)
    if not changed:
        return "pytest tests/"
    test_files = []
    for src in changed[:4]:  # limit to 4 files
        tf = _find_test_file(src, project_root)
        if tf not in test_files:
            test_files.append(tf)
    if len(test_files) == 1:
        return f"pytest {test_files[0]} -v"
    files_str = " ".join(test_files)
    return f"pytest {files_str}"


def _is_pre_push_context(history: list, cmd: str) -> bool:
    """True if this test run looks like it's before a git push/commit."""
    recent_cmds = [
        e.get("summary", "") for e in history[-10:]
        if e.get("tool_name") == "Bash"
    ]
    push_signals = any(
        "git push" in s or "git commit" in s or "git add" in s
        for s in recent_cmds
    )
    return push_signals


def _webfetch_domain_count(history: list, url: str) -> int:
    if not url:
        return 0
    try:
        domain = url.split("/")[2]
    except IndexError:
        return 0
    return sum(
        1 for e in history
        if e.get("tool_name") == "WebFetch"
        and domain in e.get("summary", "")
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

    # full_test_run: running full test suite when targeted run is better
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if re.search(r"\bpytest\b|\bnpm test\b|\bcargo test\b", cmd):
            if not re.search(r"\b-k\b|\btest_\w+\.py\b|::\w+|tests/test_", cmd):
                # Pre-push context: full run is correct — don't warn
                if not _is_pre_push_context(history, cmd):
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

    # write_instead_of_edit: Write on existing file
    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        if path and os.path.exists(path):
            found.append("write_instead_of_edit")

    # no_git_commit: >10 edits since last git commit
    if tool_name in ("Edit", "Write") and _edits_since_last_commit(history) > 10:
        found.append("no_git_commit")

    # edit_unread_file: editing a large file that wasn't read this session
    # Only fire after 5+ events AND only for non-trivial files (>100 lines)
    if tool_name in ("Edit", "Write") and len(history) >= 5:
        path = tool_input.get("file_path", "")
        if path and not _file_was_read(history, path):
            try:
                with open(path) as _f:
                    file_lines = sum(1 for _ in _f)
                if file_lines > 100:
                    found.append("edit_unread_file")
            except OSError:
                pass

    # long_session: session > 100 events
    if _session_event_count(history) > 100:
        found.append("long_session")

    # missing_tests: 5+ src edits in this session with zero test files touched
    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        if _is_src_file(path) and not _has_test_write_in_session(history):
            src_edits = sum(
                1 for e in history
                if e.get("tool_name") in ("Edit", "Write") and _is_src_file(e.get("file_path", ""))
            )
            if src_edits >= 4:  # 4 past + current = 5 total
                found.append("missing_tests")

    # webfetch_repeated: same domain fetched 3+ times
    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        if _webfetch_domain_count(history, url) >= 2:
            found.append("webfetch_repeated")

    # chained_destructive: rm && ...
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if re.search(r"\brm\b.*&&", cmd):
            found.append("chained_destructive")

    # no_specific_target: Agent with no file path or function reference
    if tool_name == "Agent":
        desc = tool_input.get("description", tool_input.get("prompt", ""))
        if len(desc) > 0 and not re.search(r'[./]|def |class |function ', desc):
            found.append("no_specific_target")

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
            command = p["command"]

            # Smart full_test_run: show exact targeted command from session history
            if pid == "full_test_run":
                smart_cmd = _smart_test_command(history, project_root)
                changed = _get_changed_src_files(history)
                changed_names = ", ".join(os.path.basename(f) for f in changed[:3])
                if changed_names:
                    right_way = f"You changed: {changed_names}. Run only those tests."
                    command = smart_cmd
                else:
                    command = smart_cmd
                # Add pre-push advice
                right_way += "  Full suite: only before git push."

            # Smart missing_tests: show specific test file to create/update
            if pid == "missing_tests":
                path = tool_input.get("file_path", "")
                if path and _is_src_file(path):
                    test_file = _find_test_file(path, project_root)
                    right_way = f"Update {test_file} with tests for your changes"
                    command = f"pytest {test_file} -v"

            if trajectory:
                right_way = f"{right_way}  ({trajectory})"
            result.append(Coaching(
                pattern_id=pid,
                title=p["title"],
                problem=p["problem"],
                right_way=right_way,
                command=command,
                severity=p["severity"],
            ))
            record_pattern(pid)

    return result
