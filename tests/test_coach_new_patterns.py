"""Tests for the 8 new coach patterns added in v4."""

import os
import pytest
from unittest.mock import patch
from core.coach import detect_patterns


def _make_history(edits=0, reads=None, bash_cmds=None, webfetches=None):
    history = []
    for fp in (reads or []):
        history.append({"tool_name": "Read", "file_path": fp, "summary": f"Read {fp}", "risk": "safe"})
    for cmd in (bash_cmds or []):
        history.append({"tool_name": "Bash", "summary": cmd, "risk": "safe"})
    for _ in range(edits):
        history.append({"tool_name": "Edit", "file_path": "/tmp/src.py", "summary": "Edit", "risk": "caution"})
    for url in (webfetches or []):
        history.append({"tool_name": "WebFetch", "summary": url, "risk": "safe"})
    return history


class TestWriteInsteadOfEdit:
    def test_triggers_on_existing_file(self, tmp_path):
        f = tmp_path / "existing.py"
        f.write_text("hello")
        result = detect_patterns("Write", {"file_path": str(f)}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "write_instead_of_edit" in ids

    def test_no_trigger_for_new_file(self, tmp_path):
        f = tmp_path / "new_file.py"
        # file does NOT exist
        result = detect_patterns("Write", {"file_path": str(f)}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "write_instead_of_edit" not in ids


class TestNoGitCommit:
    def test_triggers_after_many_edits(self, tmp_path):
        history = _make_history(edits=11)
        result = detect_patterns("Edit", {"file_path": "/tmp/f.py"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_git_commit" in ids

    def test_no_trigger_after_recent_commit(self, tmp_path):
        history = _make_history(edits=5, bash_cmds=["git commit -m 'save'"])
        # 5 edits total, but commit happened between them — counter resets
        result = detect_patterns("Edit", {"file_path": "/tmp/f.py"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_git_commit" not in ids

    def test_no_trigger_when_few_edits(self, tmp_path):
        history = _make_history(edits=5)
        result = detect_patterns("Edit", {"file_path": "/tmp/f.py"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_git_commit" not in ids


class TestEditUnreadFile:
    def test_triggers_when_file_not_read(self, tmp_path):
        result = detect_patterns("Edit", {"file_path": "/tmp/unread.py"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "edit_unread_file" in ids

    def test_no_trigger_when_file_was_read(self, tmp_path):
        history = _make_history(reads=["/tmp/known.py"])
        result = detect_patterns("Edit", {"file_path": "/tmp/known.py"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "edit_unread_file" not in ids


class TestLongSession:
    def test_triggers_above_100(self, tmp_path):
        history = [{"tool_name": "Bash", "summary": f"op {i}", "risk": "safe"} for i in range(101)]
        result = detect_patterns("Bash", {"command": "ls"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "long_session" in ids

    def test_no_trigger_below_100(self, tmp_path):
        history = [{"tool_name": "Bash", "summary": f"op {i}", "risk": "safe"} for i in range(80)]
        result = detect_patterns("Bash", {"command": "ls"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "long_session" not in ids


class TestMissingTests:
    def test_triggers_when_no_test_written(self, tmp_path):
        # Create CLAUDE.md so no_claude_md doesn't fire; populate history so
        # edit_unread_file doesn't fire either — this lets missing_tests surface.
        (tmp_path / "CLAUDE.md").write_text("# project")
        fp = str(tmp_path / "core" / "cost.py")
        history = [
            {"tool_name": "Read", "file_path": fp, "summary": "read", "risk": "safe"},
        ] * 5  # file was read, session is not too fresh
        result = detect_patterns("Edit", {"file_path": fp}, history, "sonnet", str(tmp_path), max_tips=5)
        ids = [c.pattern_id for c in result]
        assert "missing_tests" in ids

    def test_no_trigger_when_test_written(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# project")
        fp = str(tmp_path / "core" / "cost.py")
        history = [
            {"tool_name": "Read", "file_path": fp, "summary": "read", "risk": "safe"},
            {"tool_name": "Edit", "file_path": str(tmp_path / "tests" / "test_cost.py"), "summary": "edit test", "risk": "caution"},
        ]
        result = detect_patterns("Edit", {"file_path": fp}, history, "sonnet", str(tmp_path), max_tips=5)
        ids = [c.pattern_id for c in result]
        assert "missing_tests" not in ids

    def test_no_trigger_for_test_file_itself(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# project")
        fp = str(tmp_path / "tests" / "test_cost.py")
        history = [{"tool_name": "Read", "file_path": fp, "summary": "read", "risk": "safe"}] * 5
        result = detect_patterns("Edit", {"file_path": fp}, history, "sonnet", str(tmp_path), max_tips=5)
        ids = [c.pattern_id for c in result]
        assert "missing_tests" not in ids


class TestWebfetchRepeated:
    def test_triggers_on_third_fetch(self, tmp_path):
        history = _make_history(webfetches=["https://docs.example.com/page1", "https://docs.example.com/page2"])
        result = detect_patterns("WebFetch", {"url": "https://docs.example.com/page3"}, history, "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "webfetch_repeated" in ids

    def test_no_trigger_on_first_fetch(self, tmp_path):
        result = detect_patterns("WebFetch", {"url": "https://docs.example.com/page1"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "webfetch_repeated" not in ids


class TestChainedDestructive:
    def test_triggers_on_rm_and_chain(self, tmp_path):
        result = detect_patterns("Bash", {"command": "rm -rf dist && npm build"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "chained_destructive" in ids

    def test_no_trigger_rm_alone(self, tmp_path):
        result = detect_patterns("Bash", {"command": "rm -rf dist"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "chained_destructive" not in ids

    def test_no_trigger_non_destructive_chain(self, tmp_path):
        result = detect_patterns("Bash", {"command": "npm build && npm test"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "chained_destructive" not in ids


class TestNoSpecificTarget:
    def test_triggers_on_vague_description(self, tmp_path):
        result = detect_patterns("Agent", {"description": "fix the bug in my code"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_specific_target" in ids

    def test_no_trigger_with_file_path(self, tmp_path):
        result = detect_patterns("Agent", {"description": "refactor core/cost.py to add caching"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_specific_target" not in ids

    def test_no_trigger_with_function_name(self, tmp_path):
        result = detect_patterns("Agent", {"description": "add def calculate_budget to cost module"}, [], "sonnet", str(tmp_path))
        ids = [c.pattern_id for c in result]
        assert "no_specific_target" not in ids
