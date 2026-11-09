"""Tests for workflow pattern recognition."""

import time
import pytest
from core.patterns import categorize, detect_workflow, detect_file_heat, WorkflowMatch


class TestCategorize:
    def test_read(self):
        assert categorize("Read") == "read"

    def test_edit(self):
        assert categorize("Edit") == "edit"

    def test_write(self):
        assert categorize("Write") == "write"

    def test_search_tools(self):
        assert categorize("Grep") == "search"
        assert categorize("Glob") == "search"
        assert categorize("Search") == "search"

    def test_bash_git_inspect(self):
        assert categorize("Bash", "git status") == "git-inspect"
        assert categorize("Bash", "git log --oneline") == "git-inspect"
        assert categorize("Bash", "git diff HEAD") == "git-inspect"

    def test_bash_git_stage(self):
        assert categorize("Bash", "git add file") == "git-stage"
        assert categorize("Bash", "git commit -m 'fix'") == "git-stage"

    def test_bash_git_push(self):
        assert categorize("Bash", "git push origin main") == "git-push"

    def test_bash_test(self):
        assert categorize("Bash", "pytest tests/") == "test"
        assert categorize("Bash", "npm test") == "test"
        assert categorize("Bash", "cargo test") == "test"

    def test_bash_explore(self):
        assert categorize("Bash", "lists directory") == "explore"
        assert categorize("Bash", "Read-only / informational") == "explore"

    def test_bash_build(self):
        assert categorize("Bash", "npm install packages") == "build"
        assert categorize("Bash", "cargo build project") == "build"

    def test_bash_generic(self):
        assert categorize("Bash", "some random command") == "bash"


class TestDetectWorkflow:
    def _event(self, tool, summary="", file_path=None):
        return {
            "timestamp": time.time(),
            "tool_name": tool,
            "summary": summary,
            "file_path": file_path,
            "risk": "safe",
        }

    def test_explore_pattern(self):
        history = [
            self._event("Read", "read"),
            self._event("Grep", "search"),
        ]
        result = detect_workflow(history, "Read", "read")
        assert result is not None
        assert result.name == "explore"

    def test_modify_pattern(self):
        history = [
            self._event("Read", "read", "/tmp/foo.py"),
        ]
        result = detect_workflow(history, "Edit", "edit", "/tmp/foo.py")
        assert result is not None
        assert result.name == "modify"

    def test_modify_with_file_match_boosts_confidence(self):
        history = [
            self._event("Read", "read", "/tmp/foo.py"),
        ]
        result = detect_workflow(history, "Edit", "edit", "/tmp/foo.py")
        assert result is not None
        assert result.confidence > 0.5

    def test_verify_edit_pattern(self):
        history = [
            self._event("Edit", "edit", "/tmp/foo.py"),
        ]
        result = detect_workflow(history, "Read", "read", "/tmp/foo.py")
        assert result is not None
        assert result.name == "verify-edit"

    def test_multi_edit_pattern(self):
        history = [
            self._event("Edit", "edit", "/tmp/a.py"),
        ]
        result = detect_workflow(history, "Edit", "edit", "/tmp/b.py")
        assert result is not None
        assert result.name == "multi-edit"

    def test_fix_cycle_pattern(self):
        history = [
            self._event("Edit", "edit", "/tmp/foo.py"),
        ]
        result = detect_workflow(history, "Bash", "pytest tests/")
        assert result is not None
        assert result.name == "fix-cycle"

    def test_commit_flow(self):
        history = [
            self._event("Bash", "git add file"),
        ]
        result = detect_workflow(history, "Bash", "git commit -m fix")
        assert result is not None
        assert result.name == "commit-flow"

    def test_no_pattern_on_empty_history(self):
        result = detect_workflow([], "Read", "read")
        assert result is None

    def test_no_pattern_for_single_unrelated(self):
        history = [
            self._event("Agent", "spawning agent"),
        ]
        result = detect_workflow(history, "WebFetch", "fetching")
        assert result is None


class TestFileHeat:
    def test_no_heat(self):
        assert detect_file_heat([], "/tmp/foo.py") == 0

    def test_heat_counts(self):
        events = [
            {"file_path": "/tmp/foo.py"},
            {"file_path": "/tmp/bar.py"},
            {"file_path": "/tmp/foo.py"},
            {"file_path": "/tmp/foo.py"},
        ]
        assert detect_file_heat(events, "/tmp/foo.py") == 3
        assert detect_file_heat(events, "/tmp/bar.py") == 1

    def test_none_path(self):
        assert detect_file_heat([{"file_path": "/tmp/a"}], None) == 0
