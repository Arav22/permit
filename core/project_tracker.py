"""Cross-session project tracking.

Persists aggregated session data to .permit/project.json in the project root.
Each PostToolUse call rolls up the current session's stats so there is no
"session end" event needed — we just keep overwriting the current session entry.
"""

import json
import os
import time
from datetime import datetime


def _project_file(project_root: str = "") -> str:
    root = project_root or os.getcwd()
    return os.path.join(root, ".permit", "project.json")


def _get_session_id() -> str:
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    return str(os.getppid())


def load_project_data(project_root: str = "") -> dict:
    path = _project_file(project_root)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "project": os.path.basename(os.getcwd()),
            "created_at": time.time(),
            "total_cost_usd": 0.0,
            "total_sessions": 0,
            "total_operations": 0,
            "sessions": [],
        }


def _save_project_data(data: dict, project_root: str = ""):
    path = _project_file(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def update_session(
    tool_name: str,
    file_path: str,
    risk: str,
    cost_usd: float,
    model: str,
    patterns: list[str],
    project_root: str = "",
):
    """Upsert the current session entry with one more operation."""
    session_id = _get_session_id()
    data = load_project_data(project_root)

    sessions = data.setdefault("sessions", [])
    today = datetime.now().strftime("%Y-%m-%d")

    # Find or create current session entry
    session = None
    for s in sessions:
        if s.get("session_id") == session_id:
            session = s
            break

    if session is None:
        session = {
            "session_id": session_id,
            "date": today,
            "start_time": time.time(),
            "last_updated": time.time(),
            "cost_usd": 0.0,
            "operation_count": 0,
            "risk_counts": {"safe": 0, "caution": 0, "danger": 0},
            "files_changed": [],
            "model": model,
            "patterns_detected": {},
            "tool_counts": {},
        }
        sessions.append(session)
        data["total_sessions"] = len(sessions)

    # Update rolling session stats
    session["last_updated"] = time.time()
    session["cost_usd"] = round(session.get("cost_usd", 0.0) + cost_usd, 6)
    session["operation_count"] = session.get("operation_count", 0) + 1

    risk_counts = session.setdefault("risk_counts", {"safe": 0, "caution": 0, "danger": 0})
    risk_counts[risk] = risk_counts.get(risk, 0) + 1

    if file_path and file_path not in session.get("files_changed", []):
        session.setdefault("files_changed", []).append(file_path)

    tc = session.setdefault("tool_counts", {})
    tc[tool_name] = tc.get(tool_name, 0) + 1

    pd = session.setdefault("patterns_detected", {})
    for pid in patterns:
        pd[pid] = pd.get(pid, 0) + 1

    # Update project totals
    data["total_cost_usd"] = round(sum(s.get("cost_usd", 0) for s in sessions), 6)
    data["total_operations"] = sum(s.get("operation_count", 0) for s in sessions)

    _save_project_data(data, project_root)
