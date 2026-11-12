"""Tests for command discovery hints."""

import pytest
from unittest.mock import patch, MagicMock
from core.discovery import detect_hints, Hint, _hint_seen_count


def _empty_history():
    return []


def _history(n):
    return [{"tool_name": "Bash", "summary": f"op{i}", "risk": "safe"} for i in range(n)]


class TestHintResume:
    def test_fires_on_first_op(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _empty_history(), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_resume" in ids

    def test_does_not_fire_mid_session(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _history(5), False, str(tmp_path))
        # hint_resume should not be in results (n != 0)
        ids = [h.hint_id for h in hints]
        assert "hint_resume" not in ids


class TestHintCompact:
    def test_fires_at_30_events(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=True):
            hints = detect_hints("Bash", {"command": "ls"}, _history(30), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_compact" in ids

    def test_does_not_fire_below_30(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=True):
            hints = detect_hints("Bash", {"command": "ls"}, _history(15), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_compact" not in ids


class TestHintInit:
    def test_fires_when_no_claude_md(self, tmp_path):
        # Use history of 3-5 so hint_model (n<=2) doesn't fire first
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=False):
            hints = detect_hints("Read", {"file_path": str(tmp_path / "f.py")}, _history(4), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_init" in ids

    def test_does_not_fire_when_claude_md_exists(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# project")
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Read", {"file_path": str(tmp_path / "f.py")}, _history(2), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_init" not in ids


class TestHintRollback:
    def test_fires_when_snapshot_saved(self, tmp_path):
        # Use non-empty history so hint_resume (n==0) doesn't fire first
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=True):
            hints = detect_hints("Edit", {"file_path": "/tmp/f.py"}, _history(4), True, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_rollback" in ids

    def test_does_not_fire_without_snapshot(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=True):
            hints = detect_hints("Edit", {"file_path": "/tmp/f.py"}, _history(4), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_rollback" not in ids


class TestHintSuppression:
    def test_suppressed_after_3_appearances(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=3), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _empty_history(), False, str(tmp_path))
        # hint_resume would fire (n==0) but is suppressed after 3 appearances
        assert len(hints) == 0

    def test_shown_before_3_appearances(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=2), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _empty_history(), False, str(tmp_path))
        # hint_resume fires (n==0) and seen count < 3, so shown
        assert len(hints) == 1


class TestHintProjectReport:
    def test_fires_with_multiple_session_dates(self, tmp_path):
        project_data = {"sessions": [
            {"date": "2026-11-01"},
            {"date": "2026-11-02"},
        ]}
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value=project_data), \
             patch("core.discovery.get_session_cost", return_value=0), \
             patch("core.discovery._has_claude_md", return_value=True):
            hints = detect_hints("Bash", {"command": "ls"}, _history(5), False, str(tmp_path))
        ids = [h.hint_id for h in hints]
        assert "hint_project_report" in ids


class TestMaxOneHintPerBox:
    def test_at_most_one_hint_returned(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": [{"date": "2026-11-01"}, {"date": "2026-11-02"}]}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _history(20), True, str(tmp_path))
        assert len(hints) <= 1


class TestHintOneLiner:
    def test_one_liner_contains_command(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints("Bash", {"command": "ls"}, _empty_history(), False, str(tmp_path))
        if hints:
            assert "/" in hints[0].one_liner or "permit" in hints[0].one_liner
