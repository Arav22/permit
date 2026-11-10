"""Smart rollback -- snapshot files before modifications."""

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Snapshot:
    snapshot_id: str
    original_path: str
    timestamp: float
    snapshot_file: str
    summary: str
    size_bytes: int


@dataclass
class RollbackCheck:
    snapshot: Snapshot
    dependent_files: list[str]
    warnings: list[str]
    safe: bool


def _snapshots_dir() -> str:
    d = os.path.join(os.getcwd(), ".permit", "snapshots")
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path() -> str:
    return os.path.join(_snapshots_dir(), "manifest.json")


def _load_manifest() -> dict:
    path = _manifest_path()
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_manifest(manifest: dict):
    path = _manifest_path()
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def _is_binary(file_path: str, check_bytes: int = 8192) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(check_bytes)
            return b"\x00" in chunk
    except OSError:
        return True


def create_snapshot(
    file_path: str,
    summary: str,
    max_file_size: int = 1_048_576,
    tool_use_id: str = "",
) -> Optional[str]:
    if not os.path.exists(file_path):
        return None
    if _is_binary(file_path):
        return None
    try:
        size = os.path.getsize(file_path)
    except OSError:
        return None
    if size > max_file_size:
        return None

    snapshot_id = uuid.uuid4().hex[:8]
    snap_file = f"{snapshot_id}.snap"
    snap_path = os.path.join(_snapshots_dir(), snap_file)

    try:
        with open(file_path, "r") as f:
            content = f.read()
        with open(snap_path, "w") as f:
            f.write(content)
    except OSError:
        return None

    manifest = _load_manifest()
    manifest[snapshot_id] = asdict(Snapshot(
        snapshot_id=snapshot_id,
        original_path=os.path.abspath(file_path),
        timestamp=time.time(),
        snapshot_file=snap_file,
        summary=summary,
        size_bytes=size,
    ))
    if tool_use_id:
        manifest[snapshot_id]["tool_use_id"] = tool_use_id
    _save_manifest(manifest)

    return snapshot_id


def list_snapshots(file_path: Optional[str] = None, limit: int = 20) -> list[Snapshot]:
    manifest = _load_manifest()
    entries = []
    for sid, data in manifest.items():
        if file_path and data.get("original_path") != os.path.abspath(file_path):
            continue
        entries.append(Snapshot(
            snapshot_id=data.get("snapshot_id", sid),
            original_path=data.get("original_path", ""),
            timestamp=data.get("timestamp", 0),
            snapshot_file=data.get("snapshot_file", ""),
            summary=data.get("summary", ""),
            size_bytes=data.get("size_bytes", 0),
        ))
    entries.sort(key=lambda s: s.timestamp, reverse=True)
    return entries[:limit]


def find_snapshot(query: str) -> list[Snapshot]:
    all_snaps = list_snapshots(limit=100)
    query_lower = query.lower()

    exact = [s for s in all_snaps if s.original_path == query]
    if exact:
        return exact

    basename = [s for s in all_snaps if os.path.basename(s.original_path).lower() == query_lower]
    if basename:
        return basename

    substring = [s for s in all_snaps if query_lower in s.original_path.lower() or query_lower in s.summary.lower()]
    return substring


def check_rollback(snapshot_id: str) -> Optional[RollbackCheck]:
    manifest = _load_manifest()
    entry = manifest.get(snapshot_id)
    if not entry:
        return None

    snap = Snapshot(**{k: v for k, v in entry.items() if k in Snapshot.__dataclass_fields__})
    dependent_files = []
    warnings = []

    for sid, data in manifest.items():
        if sid == snapshot_id:
            continue
        if data.get("timestamp", 0) > snap.timestamp:
            dep_path = data.get("original_path", "")
            if dep_path and dep_path != snap.original_path:
                dependent_files.append(dep_path)

    if dependent_files:
        unique = sorted(set(dependent_files))
        warnings.append(f"{len(unique)} file(s) were modified after this snapshot: {', '.join(os.path.basename(f) for f in unique[:5])}")

    return RollbackCheck(
        snapshot=snap,
        dependent_files=list(set(dependent_files)),
        warnings=warnings,
        safe=len(dependent_files) == 0,
    )


def execute_rollback(snapshot_id: str) -> bool:
    manifest = _load_manifest()
    entry = manifest.get(snapshot_id)
    if not entry:
        return False

    snap_path = os.path.join(_snapshots_dir(), entry.get("snapshot_file", ""))
    original_path = entry.get("original_path", "")

    if not os.path.exists(snap_path) or not original_path:
        return False

    try:
        with open(snap_path, "r") as f:
            content = f.read()
        with open(original_path, "w") as f:
            f.write(content)
        return True
    except OSError:
        return False


def auto_cleanup(max_age_days: int = 7, max_size_mb: int = 100) -> list[str]:
    manifest = _load_manifest()
    if not manifest:
        return []

    removed = []
    now = time.time()
    max_age_seconds = max_age_days * 86400

    for sid in list(manifest.keys()):
        data = manifest[sid]
        if now - data.get("timestamp", 0) > max_age_seconds:
            _remove_snapshot(manifest, sid)
            removed.append(sid)

    total_bytes = sum(d.get("size_bytes", 0) for d in manifest.values())
    max_bytes = max_size_mb * 1_048_576

    if total_bytes > max_bytes:
        by_age = sorted(manifest.keys(), key=lambda s: manifest[s].get("timestamp", 0))
        for sid in by_age:
            if total_bytes <= max_bytes:
                break
            total_bytes -= manifest[sid].get("size_bytes", 0)
            _remove_snapshot(manifest, sid)
            removed.append(sid)

    _save_manifest(manifest)
    return removed


def _remove_snapshot(manifest: dict, snapshot_id: str):
    entry = manifest.pop(snapshot_id, None)
    if entry:
        snap_path = os.path.join(_snapshots_dir(), entry.get("snapshot_file", ""))
        try:
            os.remove(snap_path)
        except OSError:
            pass


def ensure_gitignore() -> Optional[str]:
    gitignore = os.path.join(os.getcwd(), ".gitignore")
    try:
        with open(gitignore, "r") as f:
            content = f.read()
            if ".permit" in content:
                return None
        return "Add .permit/ to your .gitignore to avoid committing snapshots"
    except FileNotFoundError:
        return "No .gitignore found -- consider adding .permit/ to prevent committing snapshots"
