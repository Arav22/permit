"""Tests for session report generation."""

import pytest
from core.report import generate_report
from unittest.mock import patch


def _make_history(n_safe=5, n_caution=3, n_danger=1, with_cost=True, with_snapshots=False):
    history = []
    for i in range(n_safe):
        e = {"tool_name": "Bash", "summary": f"ls {i}", "risk": "safe", "file_path": None}
        if with_cost:
            e["cost_estimate_usd"] = 0.001
        history.append(e)
    for i in range(n_caution):
        e = {"tool_name": "Edit", "summary": f"edit {i}", "risk": "caution", "file_path": f"/tmp/file{i}.py"}
        if with_cost:
            e["cost_estimate_usd"] = 0.005
        if with_snapshots:
            e["snapshot_id"] = f"abc{i}"
        history.append(e)
    for i in range(n_danger):
        e = {"tool_name": "Bash", "summary": f"rm {i}", "risk": "danger", "file_path": None}
        if with_cost:
            e["cost_estimate_usd"] = 0.04
        history.append(e)
    return history


class TestGenerateReport:
    def test_empty_history(self):
        result = generate_report([])
        assert "No session history" in result

    def test_contains_session_report_header(self):
        result = generate_report(_make_history())
        assert "SESSION REPORT" in result

    def test_shows_total_cost(self):
        history = _make_history(n_safe=2, n_caution=0, n_danger=0)
        result = generate_report(history)
        assert "~$" in result

    def test_shows_operations_count(self):
        history = _make_history(n_safe=5, n_caution=3, n_danger=1)
        result = generate_report(history)
        assert "9 total" in result

    def test_shows_risk_breakdown(self):
        history = _make_history(n_safe=5, n_caution=3, n_danger=1)
        result = generate_report(history)
        assert "Safe:" in result or "safe" in result.lower()
        assert "Danger:" in result or "danger" in result.lower()

    def test_shows_files_touched(self):
        history = _make_history(n_caution=3)
        result = generate_report(history)
        assert "Files touched" in result

    def test_shows_snapshots(self):
        history = _make_history(n_caution=2, with_snapshots=True)
        result = generate_report(history)
        assert "Snapshot" in result

    def test_no_snapshots_section_when_none(self):
        history = _make_history(with_snapshots=False)
        result = generate_report(history)
        assert "snapshot" not in result.lower() or "0 snapshot" in result.lower()

    def test_box_borders_aligned(self):
        history = _make_history()
        result = generate_report(history)
        for line in result.strip().split("\n"):
            if line.startswith("+"):
                assert line.endswith("+"), f"Border not closed: {line!r}"
            elif line.startswith("|"):
                assert line.endswith("|"), f"Right border missing: {line!r}"

    def test_learning_section_shown_with_data(self):
        with patch("core.report.get_learning_stats") as mock:
            mock.return_value = {
                "opus_for_coding": {"count": 5, "sessions": 3, "last_seen": 0}
            }
            history = _make_history()
            result = generate_report(history)
            assert "Learning" in result
            assert "opus for coding" in result.lower()
