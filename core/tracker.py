"""Session history tracker — remembers tool calls across a session.

Uses CLAUDE_SESSION_ID when available, falls back to PPID-based session files.
Tracks file heat (how many times each file is touched) and operation patterns.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ToolEvent:
    timestamp: float
    tool_name: str
    summary: str
    file_path: Optional[str] = None
    risk: str = "safe"
    denied: bool = False


def _session_file() -> str:
    """Determine the session history file path."""
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    session_id = os.environ.get("CLAUDE_SESSION_ID")
    if session_id:
        return os.path.join(tmpdir, f"permit-session-{session_id}.json")
    ppid = os.getppid()
    return os.path.join(tmpdir, f"permit-session-{ppid}.json")


def _latest_file() -> str:
    """Shared file for the /permit skill to read from."""
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    return os.path.join(tmpdir, "permit-history-latest.json")


def _load_history() -> list[dict]:
    """Load session history, preferring session-specific file."""
    for path in [_session_file(), _latest_file()]:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    newest = data[-1].get("timestamp", 0)
                    if time.time() - newest < 7200:  # 2h window
                        return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue
    return []


def _save_history(history: list[dict]):
    """Persist history to both session-specific and latest files."""
    trimmed = history[-100:]  # keep last 100 events
    for path in [_session_file(), _latest_file()]:
        try:
            with open(path, "w") as f:
                json.dump(trimmed, f)
        except OSError:
            continue


def record_event(tool_name: str, summary: str, file_path: Optional[str] = None,
                 risk: str = "safe", denied: bool = False):
    """Record a tool event in session history."""
    history = _load_history()
    event = ToolEvent(
        timestamp=time.time(),
        tool_name=tool_name,
        summary=summary,
        file_path=file_path,
        risk=risk,
        denied=denied,
    )
    history.append(asdict(event))
    _save_history(history)


def get_history() -> list[dict]:
    """Get the full session history."""
    return _load_history()


def get_chain(limit: int = 5) -> list[dict]:
    """Get the most recent operation chain."""
    history = _load_history()
    return history[-limit:]


def find_related(tool_name: str, file_path: Optional[str] = None, limit: int = 3) -> list[dict]:
    """Find recent related operations by tool name or file path."""
    history = _load_history()
    related = []
    for event in reversed(history):
        if len(related) >= limit:
            break
        if file_path and event.get("file_path") == file_path:
            related.append(event)
        elif event.get("tool_name") == tool_name:
            related.append(event)
    return list(reversed(related))


def format_chain(chain: list[dict], current_summary: str) -> str:
    """Format an operation chain as a text diagram."""
    if not chain:
        return ""

    lines = []
    for i, event in enumerate(chain):
        prefix = "   |- "
        elapsed = time.time() - event.get("timestamp", time.time())
        if elapsed < 60:
            ago = f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            ago = f"{int(elapsed / 60)}m ago"
        else:
            ago = f"{int(elapsed / 3600)}h ago"

        summary = event.get("summary", "unknown")
        lines.append(f"{prefix}{summary} ({ago})")

    lines.append(f"   '- {current_summary} (now)")
    return "\n".join(lines)


def _shorten(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    parts = path.split("/")
    if len(parts) > 4:
        return parts[0] + "/" + parts[1] + "/.../" + "/".join(parts[-2:])
    return path
