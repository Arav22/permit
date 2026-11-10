"""Tests for Claude Code anti-pattern detection."""

import json
import os
import pytest
from core.coach import (
    detect_patterns,
    record_pattern,
    get_learning_stats,
    format_trajectory,
    _has_claude_md,
    _same_file_read_count,
    Coaching,
)


@pytest.fixture
def no_learning(tmp_path, monkeypatch):
    """Redirect learning file to tmp_path so tests don't pollute ~/.claude."""
    learning_path = tmp_path / "permit-learning.json"
    monkeypatch.setattr("core.coach._LEARNING_FILE", str(learning_path))
    return learning_path


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestDetectPatterns:
    def test_opus_for_coding_bash(self, project_dir, no_learning):
        results = detect_patterns("Bash", {"command": "ls"}, [], "opus", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "opus_for_coding" in ids

    def test_opus_for_coding_edit(self, project_dir, no_learning):
        results = detect_patterns("Edit", {"file_path": "/tmp/f.py"}, [], "opus", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "opus_for_coding" in ids

    def test_no_opus_tip_on_sonnet(self, project_dir, no_learning):
        results = detect_patterns("Bash", {"command": "ls"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "opus_for_coding" not in ids

    def test_context_bloat(self, project_dir, no_learning):
        history = [{"tool_name": "Bash", "summary": f"cmd {i}"} for i in range(55)]
        results = detect_patterns("Bash", {"command": "ls"}, history, "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "context_bloat" in ids

    def test_no_context_bloat_small_session(self, project_dir, no_learning):
        history = [{"tool_name": "Bash"} for _ in range(10)]
        results = detect_patterns("Bash", {"command": "ls"}, history, "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "context_bloat" not in ids

    def test_big_read_no_limit(self, project_dir, no_learning):
        f = project_dir / "big.py"
        f.write_text("x\n" * 600)
        results = detect_patterns("Read", {"file_path": str(f)}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "big_read_no_limit" in ids

    def test_big_read_with_limit_ok(self, project_dir, no_learning):
        f = project_dir / "big.py"
        f.write_text("x\n" * 600)
        results = detect_patterns("Read", {"file_path": str(f), "limit": 50}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "big_read_no_limit" not in ids

    def test_full_test_run(self, project_dir, no_learning):
        results = detect_patterns("Bash", {"command": "pytest"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "full_test_run" in ids

    def test_targeted_test_ok(self, project_dir, no_learning):
        results = detect_patterns("Bash", {"command": "pytest tests/test_cost.py"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "full_test_run" not in ids

    def test_agent_overkill(self, project_dir, no_learning):
        results = detect_patterns("Agent", {"description": "search files"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "agent_overkill" in ids

    def test_no_claude_md(self, project_dir, no_learning):
        results = detect_patterns("Read", {"file_path": "/tmp/f.py"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "no_claude_md" in ids

    def test_has_claude_md(self, project_dir, no_learning):
        (project_dir / "CLAUDE.md").write_text("# Project")
        results = detect_patterns("Read", {"file_path": "/tmp/f.py"}, [], "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "no_claude_md" not in ids

    def test_repeated_large_read(self, project_dir, no_learning):
        path = "/tmp/analyzer.py"
        history = [
            {"tool_name": "Read", "file_path": path},
            {"tool_name": "Read", "file_path": path},
            {"tool_name": "Read", "file_path": path},
        ]
        results = detect_patterns("Read", {"file_path": path}, history, "sonnet", str(project_dir))
        ids = [c.pattern_id for c in results]
        assert "repeated_large_read" in ids

    def test_max_tips_respected(self, project_dir, no_learning):
        history = [{"tool_name": "Bash"} for _ in range(55)]
        results = detect_patterns("Bash", {"command": "pytest"}, history, "opus", str(project_dir), max_tips=1)
        assert len(results) <= 1

    def test_coaching_has_right_fields(self, project_dir, no_learning):
        results = detect_patterns("Bash", {"command": "ls"}, [], "opus", str(project_dir))
        assert len(results) > 0
        c = results[0]
        assert c.pattern_id
        assert c.title
        assert c.problem
        assert c.right_way
        assert c.severity in ("tip", "warning")


class TestLearningTrajectory:
    def test_record_and_load(self, no_learning):
        record_pattern("opus_for_coding")
        stats = get_learning_stats()
        assert "opus_for_coding" in stats
        assert stats["opus_for_coding"]["count"] == 1

    def test_increments(self, no_learning):
        record_pattern("context_bloat")
        record_pattern("context_bloat")
        record_pattern("context_bloat")
        stats = get_learning_stats()
        assert stats["context_bloat"]["count"] == 3

    def test_format_trajectory_first_time(self, no_learning):
        result = format_trajectory("opus_for_coding")
        assert result == ""

    def test_format_trajectory_repeated(self, no_learning):
        for _ in range(5):
            record_pattern("opus_for_coding")
        result = format_trajectory("opus_for_coding")
        assert "5 times" in result or "fix it" in result.lower()


class TestHelpers:
    def test_has_claude_md_present(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Project")
        assert _has_claude_md(str(tmp_path)) is True

    def test_has_claude_md_missing(self, tmp_path):
        assert _has_claude_md(str(tmp_path)) is False

    def test_same_file_read_count(self):
        history = [
            {"tool_name": "Read", "file_path": "/tmp/f.py"},
            {"tool_name": "Edit", "file_path": "/tmp/f.py"},
            {"tool_name": "Read", "file_path": "/tmp/f.py"},
        ]
        assert _same_file_read_count(history, "/tmp/f.py") == 2

    def test_same_file_read_count_zero(self):
        history = [{"tool_name": "Bash", "file_path": None}]
        assert _same_file_read_count(history, "/tmp/f.py") == 0
