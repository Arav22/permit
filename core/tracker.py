"""Session history tracker — remembers past tool calls to show connections."""

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


HISTORY_FILE = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    f"permit-history-{os.getpid()}.json",
)

SESSION_FILE = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "permit-history-latest.json",
)


def _load_history() -> list:
    for path in [SESSION_FILE, HISTORY_FILE]:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    newest = data[-1].get("timestamp", 0)
                    if time.time() - newest < 3600:
                        return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue
    return []


def _save_history(history: list):
    trimmed = history[-50:]
    for path in [SESSION_FILE, HISTORY_FILE]:
        try:
            with open(path, "w") as f:
                json.dump(trimmed, f)
            break
        except OSError:
            continue


def record_event(tool_name: str, summary: str, file_path: Optional[str] = None, risk: str = "safe"):
    history = _load_history()
    event = ToolEvent(
        timestamp=time.time(),
        tool_name=tool_name,
        summary=summary,
        file_path=file_path,
        risk=risk,
    )
    history.append(asdict(event))
    _save_history(history)


def find_related(tool_name: str, file_path: Optional[str] = None, limit: int = 3) -> list:
    """Find recent related operations."""
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


def get_chain(limit: int = 5) -> list:
    """Get the most recent operation chain."""
    history = _load_history()
    return history[-limit:]


def format_chain(chain: list, current_summary: str) -> str:
    """Format an operation chain as a dependency diagram."""
    if not chain:
        return ""

    lines = []
    for i, event in enumerate(chain):
        prefix = "   ├─ " if i < len(chain) - 1 else "   └─ "
        elapsed = time.time() - event.get("timestamp", time.time())
        if elapsed < 60:
            ago = f"{int(elapsed)}s ago"
        else:
            ago = f"{int(elapsed / 60)}m ago"
        lines.append(f"{prefix}{event['summary']} ({ago})")

    lines.append(f"   └─ {current_summary} (now)")

    return "\n".join(lines)
