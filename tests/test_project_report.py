"""Tests for cross-session project report generator."""

import json
import os
import pytest
from unittest.mock import patch
from core.project_report import generate_project_report, generate_html_report, _ascii_bar


def _make_project_data(n_sessions=3, with_patterns=False):
    sessions = []
    for i in range(n_sessions):
        s = {
            "session_id": f"sess-{i}",
            "date": f"2026-11-0{i + 1}",
            "start_time": 1000000 + i * 3600,
            "last_updated": 1000000 + i * 3600 + 1800,
            "cost_usd": 0.5 + i * 0.3,
            "operation_count": 20 + i * 5,
            "risk_counts": {"safe": 10, "caution": 5, "danger": 1},
            "files_changed": [f"/proj/core/file{i}.py", "/proj/hooks/pre.py"],
            "model": "opus",
            "patterns_detected": {"context_bloat": i + 1} if with_patterns else {},
            "tool_counts": {"Read": 10 + i, "Edit": 5, "Bash": 5},
        }
        sessions.append(s)
    return {
        "project": "myproject",
        "created_at": 1000000,
        "total_cost_usd": sum(s["cost_usd"] for s in sessions),
        "total_sessions": n_sessions,
        "total_operations": sum(s["operation_count"] for s in sessions),
        "sessions": sessions,
    }


class TestGenerateProjectReport:
    def test_empty_sessions(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = {"sessions": []}
            result = generate_project_report("summary", str(tmp_path))
            assert "No project history" in result

    def test_contains_project_name(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            result = generate_project_report("summary", str(tmp_path))
            assert "myproject" in result

    def test_shows_total_cost(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            result = generate_project_report("summary", str(tmp_path))
            assert "~$" in result

    def test_shows_session_bar_chart(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(3)
            result = generate_project_report("summary", str(tmp_path))
            assert "2026-11-0" in result
            assert "[" in result and "]" in result

    def test_shows_tools_section(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            result = generate_project_report("summary", str(tmp_path))
            assert "Read" in result or "Edit" in result

    def test_shows_coach_trends_with_patterns(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(3, with_patterns=True)
            result = generate_project_report("summary", str(tmp_path))
            assert "context bloat" in result.lower() or "Coach" in result

    def test_box_borders_aligned(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            result = generate_project_report("summary", str(tmp_path))
            for line in result.strip().split("\n"):
                stripped = line.strip("\033[0m").rstrip()
                if stripped.startswith("+"):
                    assert stripped.endswith("+"), f"Border not closed: {line!r}"
                elif stripped.startswith("|"):
                    assert "|" in stripped[1:], f"Right border missing: {line!r}"


class TestAsciiBar:
    def test_full_bar(self):
        bar = _ascii_bar(100, 100, 10)
        assert bar == "=========="

    def test_empty_bar(self):
        bar = _ascii_bar(0, 100, 10)
        assert bar == "----------"

    def test_half_bar(self):
        bar = _ascii_bar(50, 100, 10)
        assert bar == "=====-----"

    def test_zero_max(self):
        bar = _ascii_bar(10, 0, 10)
        assert bar == "----------"


class TestHtmlReport:
    def test_generates_html(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            html = generate_html_report(str(tmp_path))
            assert "<html>" in html
            assert "myproject" in html
            assert "Session" in html

    def test_contains_cost_data(self, tmp_path):
        with patch("core.project_report.load_project_data") as mock:
            mock.return_value = _make_project_data(2)
            html = generate_html_report(str(tmp_path))
            assert "$" in html
