"""Tests for smart rollback / snapshot system."""

import json
import os
import time
import pytest
from core.rollback import (
    create_snapshot,
    list_snapshots,
    find_snapshot,
    check_rollback,
    execute_rollback,
    auto_cleanup,
    ensure_gitignore,
    _load_manifest,
    _save_manifest,
    _is_binary,
)


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Set up a fake project directory with .permit/snapshots."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestCreateSnapshot:
    def test_basic_snapshot(self, project_dir):
        f = project_dir / "app.py"
        f.write_text("print('hello')")
        sid = create_snapshot(str(f), "Edit -- app.py")
        assert sid is not None
        assert len(sid) == 8
        snap_dir = project_dir / ".permit" / "snapshots"
        assert (snap_dir / f"{sid}.snap").exists()
        assert (snap_dir / f"{sid}.snap").read_text() == "print('hello')"

    def test_new_file_skipped(self, project_dir):
        sid = create_snapshot("/nonexistent/file.py", "Write -- new file")
        assert sid is None

    def test_binary_file_skipped(self, project_dir):
        f = project_dir / "image.bin"
        f.write_bytes(b"\x00\x01\x02\x03binary data")
        sid = create_snapshot(str(f), "Edit -- image.bin")
        assert sid is None

    def test_oversized_file_skipped(self, project_dir):
        f = project_dir / "huge.txt"
        f.write_text("x" * 100)
        sid = create_snapshot(str(f), "Edit -- huge.txt", max_file_size=50)
        assert sid is None

    def test_manifest_updated(self, project_dir):
        f = project_dir / "config.py"
        f.write_text("DEBUG = True")
        sid = create_snapshot(str(f), "Edit -- config.py")
        manifest = _load_manifest()
        assert sid in manifest
        assert manifest[sid]["original_path"] == str(f.resolve())
        assert manifest[sid]["summary"] == "Edit -- config.py"

    def test_multiple_snapshots_same_file(self, project_dir):
        f = project_dir / "app.py"
        f.write_text("v1")
        sid1 = create_snapshot(str(f), "Edit 1")
        f.write_text("v2")
        sid2 = create_snapshot(str(f), "Edit 2")
        assert sid1 != sid2
        manifest = _load_manifest()
        assert sid1 in manifest
        assert sid2 in manifest

    def test_tool_use_id_stored(self, project_dir):
        f = project_dir / "app.py"
        f.write_text("code")
        sid = create_snapshot(str(f), "Edit", tool_use_id="toolu_abc123")
        manifest = _load_manifest()
        assert manifest[sid]["tool_use_id"] == "toolu_abc123"


class TestManifest:
    def test_load_empty(self, project_dir):
        manifest = _load_manifest()
        assert manifest == {}

    def test_save_and_load(self, project_dir):
        data = {"abc12345": {"snapshot_id": "abc12345", "original_path": "/tmp/f.py"}}
        _save_manifest(data)
        loaded = _load_manifest()
        assert loaded == data


class TestIsBinary:
    def test_text_file(self, tmp_path):
        f = tmp_path / "text.py"
        f.write_text("print('hello')")
        assert _is_binary(str(f)) is False

    def test_binary_file(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"header\x00\x01data")
        assert _is_binary(str(f)) is True

    def test_missing_file(self):
        assert _is_binary("/nonexistent") is True


class TestListSnapshots:
    def test_list_all(self, project_dir):
        f = project_dir / "a.py"
        f.write_text("a")
        create_snapshot(str(f), "Edit a")
        time.sleep(0.01)
        f.write_text("b")
        create_snapshot(str(f), "Edit b")
        snaps = list_snapshots()
        assert len(snaps) == 2
        assert snaps[0].summary == "Edit b"

    def test_list_filtered(self, project_dir):
        a = project_dir / "a.py"
        b = project_dir / "b.py"
        a.write_text("a")
        b.write_text("b")
        create_snapshot(str(a), "Edit a")
        create_snapshot(str(b), "Edit b")
        snaps = list_snapshots(file_path=str(a))
        assert len(snaps) == 1
        assert "a.py" in snaps[0].original_path

    def test_list_limit(self, project_dir):
        f = project_dir / "f.py"
        for i in range(5):
            f.write_text(f"v{i}")
            create_snapshot(str(f), f"Edit {i}")
        snaps = list_snapshots(limit=3)
        assert len(snaps) == 3


class TestFindSnapshot:
    def test_exact_path(self, project_dir):
        f = project_dir / "config.py"
        f.write_text("x")
        create_snapshot(str(f), "Edit config")
        results = find_snapshot(str(f.resolve()))
        assert len(results) >= 1

    def test_basename_match(self, project_dir):
        f = project_dir / "config.py"
        f.write_text("x")
        create_snapshot(str(f), "Edit config")
        results = find_snapshot("config.py")
        assert len(results) >= 1

    def test_substring_match(self, project_dir):
        f = project_dir / "my_config.py"
        f.write_text("x")
        create_snapshot(str(f), "Edit my_config")
        results = find_snapshot("config")
        assert len(results) >= 1

    def test_no_match(self, project_dir):
        results = find_snapshot("nonexistent_file.xyz")
        assert len(results) == 0


class TestCheckRollback:
    def test_no_conflicts(self, project_dir):
        f = project_dir / "a.py"
        f.write_text("original")
        sid = create_snapshot(str(f), "Edit a")
        check = check_rollback(sid)
        assert check is not None
        assert check.safe is True
        assert len(check.warnings) == 0

    def test_dependent_files_detected(self, project_dir):
        a = project_dir / "a.py"
        b = project_dir / "b.py"
        a.write_text("a")
        sid = create_snapshot(str(a), "Edit a")
        time.sleep(0.01)
        b.write_text("b")
        create_snapshot(str(b), "Edit b")
        check = check_rollback(sid)
        assert check is not None
        assert check.safe is False
        assert len(check.dependent_files) >= 1

    def test_nonexistent_snapshot(self, project_dir):
        check = check_rollback("nonexistent")
        assert check is None


class TestExecuteRollback:
    def test_restore_content(self, project_dir):
        f = project_dir / "app.py"
        f.write_text("original content")
        sid = create_snapshot(str(f), "Edit app")
        f.write_text("modified content")
        assert execute_rollback(sid) is True
        assert f.read_text() == "original content"

    def test_snapshot_preserved(self, project_dir):
        f = project_dir / "app.py"
        f.write_text("original")
        sid = create_snapshot(str(f), "Edit app")
        f.write_text("changed")
        execute_rollback(sid)
        snap_dir = project_dir / ".permit" / "snapshots"
        assert (snap_dir / f"{sid}.snap").exists()

    def test_nonexistent_rollback(self, project_dir):
        assert execute_rollback("nonexistent") is False


class TestAutoCleanup:
    def test_age_cleanup(self, project_dir):
        f = project_dir / "old.py"
        f.write_text("old")
        sid = create_snapshot(str(f), "Edit old")
        manifest = _load_manifest()
        manifest[sid]["timestamp"] = time.time() - 86400 * 10
        _save_manifest(manifest)
        removed = auto_cleanup(max_age_days=7)
        assert sid in removed
        assert _load_manifest().get(sid) is None

    def test_size_cleanup(self, project_dir):
        sids = []
        for i in range(5):
            f = project_dir / f"f{i}.py"
            f.write_text("x" * 1000)
            sid = create_snapshot(str(f), f"Edit f{i}")
            sids.append(sid)
            time.sleep(0.01)
        removed = auto_cleanup(max_age_days=365, max_size_mb=0)
        assert len(removed) > 0

    def test_no_cleanup_when_fresh(self, project_dir):
        f = project_dir / "fresh.py"
        f.write_text("fresh")
        create_snapshot(str(f), "Edit fresh")
        removed = auto_cleanup(max_age_days=7, max_size_mb=100)
        assert len(removed) == 0


class TestGitignore:
    def test_has_permit(self, project_dir):
        (project_dir / ".gitignore").write_text(".permit/\n__pycache__/\n")
        assert ensure_gitignore() is None

    def test_missing_permit(self, project_dir):
        (project_dir / ".gitignore").write_text("__pycache__/\n")
        result = ensure_gitignore()
        assert result is not None
        assert ".permit" in result

    def test_no_gitignore(self, project_dir):
        result = ensure_gitignore()
        assert result is not None
        assert ".gitignore" in result.lower() or ".permit" in result
