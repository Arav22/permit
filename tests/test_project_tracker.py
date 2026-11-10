"""Tests for cross-session project tracker."""

import json
import os
import pytest
from core.project_tracker import update_session, load_project_data, _project_file


class TestLoadProjectData:
    def test_returns_scaffold_when_missing(self, tmp_path):
        data = load_project_data(str(tmp_path))
        assert "sessions" in data
        assert data["total_cost_usd"] == 0.0
        assert data["total_sessions"] == 0

    def test_loads_existing_data(self, tmp_path):
        project_dir = tmp_path / ".permit"
        project_dir.mkdir()
        (project_dir / "project.json").write_text(
            json.dumps({"project": "test", "sessions": [], "total_cost_usd": 1.0, "total_sessions": 2, "total_operations": 5})
        )
        data = load_project_data(str(tmp_path))
        assert data["total_cost_usd"] == 1.0


class TestUpdateSession:
    def test_creates_session_on_first_call(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-1")
        update_session("Read", "/tmp/f.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["operation_count"] == 1
        assert data["sessions"][0]["cost_usd"] == pytest.approx(0.001)

    def test_accumulates_in_same_session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-2")
        update_session("Read", "/tmp/a.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        update_session("Edit", "/tmp/b.py", "caution", 0.005, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["operation_count"] == 2
        assert data["sessions"][0]["cost_usd"] == pytest.approx(0.006)

    def test_separate_sessions_stored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-A")
        update_session("Read", "/tmp/a.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-B")
        update_session("Edit", "/tmp/b.py", "caution", 0.005, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        assert len(data["sessions"]) == 2
        assert data["total_sessions"] == 2

    def test_total_cost_aggregated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-cost-A")
        update_session("Read", "", "safe", 0.01, "opus", [], str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-cost-B")
        update_session("Edit", "", "caution", 0.05, "opus", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        assert data["total_cost_usd"] == pytest.approx(0.06)

    def test_tool_counts_tracked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-tools")
        update_session("Read", "/tmp/a.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        update_session("Read", "/tmp/b.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        update_session("Edit", "/tmp/a.py", "caution", 0.005, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        s = data["sessions"][0]
        assert s["tool_counts"]["Read"] == 2
        assert s["tool_counts"]["Edit"] == 1

    def test_risk_counts_tracked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-risk")
        update_session("Bash", "", "safe", 0.001, "sonnet", [], str(tmp_path))
        update_session("Bash", "", "danger", 0.001, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        s = data["sessions"][0]
        assert s["risk_counts"]["safe"] == 1
        assert s["risk_counts"]["danger"] == 1

    def test_patterns_tracked(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-patterns")
        update_session("Read", "", "safe", 0.001, "sonnet", ["context_bloat"], str(tmp_path))
        update_session("Edit", "", "caution", 0.005, "sonnet", ["context_bloat", "opus_for_coding"], str(tmp_path))
        data = load_project_data(str(tmp_path))
        s = data["sessions"][0]
        assert s["patterns_detected"]["context_bloat"] == 2
        assert s["patterns_detected"]["opus_for_coding"] == 1

    def test_no_duplicate_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-files")
        update_session("Read", "/tmp/a.py", "safe", 0.001, "sonnet", [], str(tmp_path))
        update_session("Edit", "/tmp/a.py", "caution", 0.005, "sonnet", [], str(tmp_path))
        data = load_project_data(str(tmp_path))
        assert data["sessions"][0]["files_changed"].count("/tmp/a.py") == 1
