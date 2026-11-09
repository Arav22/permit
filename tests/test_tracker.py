"""Tests for session history tracker."""

import json
import os
import time
import pytest
from core.tracker import record_event, get_history, get_chain, find_related, format_chain


@pytest.fixture(autouse=True)
def clean_session(tmp_path, monkeypatch):
    """Use a temp directory for session files so tests don't interfere."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-001")
    yield


class TestRecordAndRetrieve:
    def test_record_event(self):
        record_event("Bash", "Lists directory", risk="safe")
        history = get_history()
        assert len(history) == 1
        assert history[0]["tool_name"] == "Bash"
        assert history[0]["summary"] == "Lists directory"
        assert history[0]["risk"] == "safe"

    def test_multiple_events(self):
        record_event("Read", "Read file", file_path="/tmp/a.py")
        record_event("Edit", "Edit file", file_path="/tmp/a.py")
        record_event("Bash", "Run tests")
        history = get_history()
        assert len(history) == 3

    def test_file_path_tracked(self):
        record_event("Read", "Read", file_path="/tmp/foo.py")
        history = get_history()
        assert history[0]["file_path"] == "/tmp/foo.py"

    def test_denied_flag(self):
        record_event("Bash", "Dangerous cmd", denied=True)
        history = get_history()
        assert history[0]["denied"] is True

    def test_timestamps_are_recent(self):
        record_event("Bash", "test")
        history = get_history()
        assert abs(history[0]["timestamp"] - time.time()) < 5


class TestGetChain:
    def test_chain_limit(self):
        for i in range(10):
            record_event("Bash", f"cmd-{i}")
        chain = get_chain(limit=3)
        assert len(chain) == 3
        assert chain[-1]["summary"] == "cmd-9"

    def test_chain_empty(self):
        assert get_chain() == []


class TestFindRelated:
    def test_find_by_file(self):
        record_event("Read", "read", file_path="/tmp/a.py")
        record_event("Bash", "ls")
        record_event("Edit", "edit", file_path="/tmp/a.py")
        related = find_related("Write", file_path="/tmp/a.py")
        assert len(related) == 2
        assert all(r["file_path"] == "/tmp/a.py" for r in related)

    def test_find_by_tool(self):
        record_event("Bash", "ls")
        record_event("Read", "read file")
        record_event("Bash", "git status")
        related = find_related("Bash")
        assert len(related) == 2

    def test_find_limited(self):
        for i in range(10):
            record_event("Bash", f"cmd-{i}")
        related = find_related("Bash", limit=3)
        assert len(related) == 3


class TestFormatChain:
    def test_format_empty(self):
        assert format_chain([], "current") == ""

    def test_format_chain(self):
        chain = [
            {"timestamp": time.time() - 30, "summary": "Read file", "file_path": "/tmp/a.py"},
            {"timestamp": time.time() - 10, "summary": "Edit file"},
        ]
        result = format_chain(chain, "Run tests")
        assert "Read file" in result
        assert "Edit file" in result
        assert "Run tests (now)" in result
        assert "|- " in result or "'- " in result

    def test_format_shows_ago(self):
        chain = [{"timestamp": time.time() - 120, "summary": "old op"}]
        result = format_chain(chain, "new op")
        assert "2m ago" in result
