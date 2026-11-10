"""Tests for output formatting."""

import pytest
from core.analyzer import Analysis
from core.cost import CostEstimate
from core.patterns import WorkflowMatch
from core.formatter import format_explanation, format_compact


def _make_analysis(**kwargs):
    defaults = {
        "risk": "safe",
        "icon": "✅",
        "title": "ls -la",
        "explanation": "Lists directory contents",
        "scope": "Local only.",
        "blast_radius": "local",
    }
    defaults.update(kwargs)
    return Analysis(**defaults)


class TestFormatExplanation:
    def test_basic_output(self):
        result = format_explanation(_make_analysis())
        assert "SAFE" in result
        assert "ls -la" in result
        assert "Lists directory contents" in result

    def test_box_borders(self):
        result = format_explanation(_make_analysis())
        assert "+-permit-" in result
        assert "| " in result
        assert " |" in result

    def test_danger_label(self):
        result = format_explanation(_make_analysis(risk="danger", icon="⛔"))
        assert "DANGER" in result

    def test_caution_label(self):
        result = format_explanation(_make_analysis(risk="caution", icon="⚠️"))
        assert "CAUTION" in result

    def test_warnings_shown(self):
        a = _make_analysis(warnings=["SSH private key", "Sensitive path"])
        result = format_explanation(a)
        assert "SSH private key" in result
        assert "Sensitive path" in result

    def test_stages_shown(self):
        a = _make_analysis(stages=["grep: search", "wc: count lines"])
        result = format_explanation(a)
        assert "grep: search" in result
        assert "wc: count lines" in result

    def test_workflow_shown(self):
        wf = WorkflowMatch(
            name="modify",
            label="Read -> Edit",
            description="Claude read a file and now wants to modify it",
            stage=1,
            total=2,
            confidence=0.8,
        )
        result = format_explanation(_make_analysis(), workflow=wf)
        assert "Read -> Edit" in result
        assert "step 2/2" in result

    def test_file_heat_shown(self):
        result = format_explanation(_make_analysis(), file_heat=5)
        assert "5x" in result

    def test_related_chain_shown(self):
        chain = "   |- Read file (10s ago)\n   '- Edit file (5s ago)"
        result = format_explanation(_make_analysis(), related_chain=chain)
        assert "Read file" in result
        assert "Recent" in result

    def test_minimal_hides_extras(self):
        wf = WorkflowMatch("x", "X", "desc", 0, 1, 0.5)
        result = format_explanation(
            _make_analysis(stages=["a", "b"], warnings=["warn"]),
            workflow=wf,
            file_heat=3,
            related_chain="line1\nline2",
            verbosity="minimal",
        )
        assert "Scope" not in result
        assert "Recent" not in result

    def test_blast_radius_shown_for_remote(self):
        a = _make_analysis(blast_radius="remote", scope="Affects remote systems.")
        result = format_explanation(a)
        assert "Remote" in result

    def test_all_borders_aligned(self):
        result = format_explanation(_make_analysis())
        lines = result.strip().split("\n")
        for line in lines:
            if line.startswith("+"):
                assert line.endswith("+"), f"Top/bottom border not closed: {line!r}"
            elif line.startswith("|"):
                assert line.endswith("|"), f"Right border missing: {line!r}"

    def test_warnings_before_scope(self):
        a = _make_analysis(warnings=["SSH private key"])
        result = format_explanation(a)
        warn_pos = result.index("SSH private key")
        scope_pos = result.index("Scope:")
        assert warn_pos < scope_pos


class TestFormatCompact:
    def test_one_line(self):
        result = format_compact(_make_analysis())
        assert "\n" not in result
        assert "SAFE" in result

    def test_includes_explanation(self):
        result = format_compact(_make_analysis(explanation="Runs ls"))
        assert "Runs ls" in result

    def test_workflow_tag(self):
        wf = WorkflowMatch("modify", "Read -> Edit", "desc", 1, 2, 0.8)
        result = format_compact(_make_analysis(), workflow=wf)
        assert "Read -> Edit" in result

    def test_danger_compact(self):
        result = format_compact(_make_analysis(risk="danger", icon="⛔"))
        assert "DANGER" in result

    def test_compact_with_cost(self):
        cost = CostEstimate(input_tokens=100, output_tokens=50, cost_usd=0.003)
        result = format_compact(_make_analysis(), cost=cost)
        assert "~$0.003" in result


class TestCostDisplay:
    def test_cost_shown_in_box(self):
        cost = CostEstimate(input_tokens=500, output_tokens=200, cost_usd=0.005)
        result = format_explanation(_make_analysis(), cost=cost)
        assert "Cost:" in result
        assert "~$0.005" in result

    def test_session_total_shown(self):
        cost = CostEstimate(input_tokens=100, output_tokens=50, cost_usd=0.002)
        result = format_explanation(_make_analysis(), cost=cost, session_cost_usd=0.42)
        assert "Session:" in result
        assert "~$0.42" in result

    def test_tips_shown(self):
        cost = CostEstimate(input_tokens=100, output_tokens=50, cost_usd=0.01, tips=["Use offset/limit"])
        result = format_explanation(_make_analysis(), cost=cost)
        assert "TIP:" in result
        assert "offset/limit" in result

    def test_cost_hidden_when_none(self):
        result = format_explanation(_make_analysis(), cost=None)
        assert "Cost:" not in result

    def test_minimal_hides_cost(self):
        cost = CostEstimate(input_tokens=100, output_tokens=50, cost_usd=0.01)
        result = format_explanation(_make_analysis(), cost=cost, verbosity="minimal")
        assert "Cost:" not in result
        assert "TIP:" not in result

    def test_snapshot_saved_shown(self):
        result = format_explanation(_make_analysis(), snapshot_saved=True)
        assert "Snapshot saved" in result

    def test_cost_borders_aligned(self):
        cost = CostEstimate(input_tokens=500, output_tokens=200, cost_usd=0.005, tips=["Switch to Sonnet"])
        result = format_explanation(_make_analysis(), cost=cost, session_cost_usd=1.23)
        lines = result.strip().split("\n")
        for line in lines:
            if line.startswith("+"):
                assert line.endswith("+"), f"Border not closed: {line!r}"
            elif line.startswith("|"):
                assert line.endswith("|"), f"Right border missing: {line!r}"
