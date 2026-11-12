"""Tests for cost estimation."""

import pytest
from core.cost import (
    estimate_cost,
    format_cost,
    format_tokens,
    generate_tips,
    CostEstimate,
    _calculate_cost,
    _detect_model,
    _chars_to_tokens,
)


class TestTokenEstimation:
    def test_read_tokens_by_file_size(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 4000)
        result = estimate_cost("Read", {"file_path": str(f)}, "opus")
        assert result.output_tokens == 1000

    def test_read_tokens_missing_file(self):
        result = estimate_cost("Read", {"file_path": "/nonexistent"}, "opus")
        assert result.output_tokens == 1000

    def test_write_tokens(self):
        content = "a" * 400
        result = estimate_cost("Write", {"content": content}, "opus")
        assert result.input_tokens == 125

    def test_edit_tokens(self):
        result = estimate_cost("Edit", {
            "file_path": "/tmp/f.py",
            "old_string": "a" * 100,
            "new_string": "b" * 100,
        }, "opus")
        assert result.input_tokens > 50

    def test_bash_safe_cmd(self):
        result = estimate_cost("Bash", {"command": "ls -la"}, "opus")
        assert result.output_tokens == 50

    def test_bash_test_cmd(self):
        result = estimate_cost("Bash", {"command": "pytest -v"}, "opus")
        assert result.output_tokens == 1500

    def test_agent_expensive(self):
        result = estimate_cost("Agent", {"prompt": "do something"}, "opus")
        assert result.input_tokens >= 2000
        assert result.output_tokens == 5000

    def test_webfetch(self):
        result = estimate_cost("WebFetch", {"url": "https://example.com"}, "opus")
        assert result.output_tokens == 2000

    def test_unknown_tool(self):
        result = estimate_cost("FutureTool", {"data": "x"}, "opus")
        assert result.input_tokens > 0
        assert result.output_tokens == 200


class TestCostCalculation:
    def test_opus_pricing(self):
        cost = _calculate_cost(1_000_000, 0, "opus")
        assert cost == pytest.approx(15.0)

    def test_opus_output_pricing(self):
        cost = _calculate_cost(0, 1_000_000, "opus")
        assert cost == pytest.approx(75.0)

    def test_sonnet_pricing(self):
        cost = _calculate_cost(1_000_000, 0, "sonnet")
        assert cost == pytest.approx(3.0)

    def test_haiku_pricing(self):
        cost = _calculate_cost(1_000_000, 0, "haiku")
        assert cost == pytest.approx(0.8)

    def test_small_operation(self):
        cost = _calculate_cost(100, 50, "opus")
        assert cost < 0.01


class TestModelDetection:
    def test_env_opus(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4")
        assert _detect_model() == "opus"

    def test_env_sonnet(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4")
        assert _detect_model() == "sonnet"

    def test_env_haiku(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-3.5")
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        assert _detect_model() == "haiku"

    def test_default_when_no_env(self, monkeypatch):
        # When no env vars are set at all, falls back to opus
        for var in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "AWS_BEDROCK_MODEL",
                    "BEDROCK_MODEL_ID", "CLAUDE_CODE_3P_SEEDED_SONNET_DEFAULT",
                    "CLAUDE_CODE_USE_BEDROCK", "ANTHROPIC_DEFAULT_SONNET_MODEL"):
            monkeypatch.delenv(var, raising=False)
        assert _detect_model() == "opus"


class TestSmartTips:
    def test_large_file_read_tip(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"line {i}" for i in range(600)))
        tips = generate_tips("Read", {"file_path": str(f)}, 0.01, "opus")
        assert any("offset/limit" in t for t in tips)

    def test_small_file_no_tip(self, tmp_path):
        f = tmp_path / "small.py"
        f.write_text("x\n" * 10)
        tips = generate_tips("Read", {"file_path": str(f)}, 0.001, "opus")
        assert not any("offset/limit" in t for t in tips)

    def test_read_with_limit_no_tip(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("\n".join(f"line {i}" for i in range(600)))
        tips = generate_tips("Read", {"file_path": str(f), "limit": 50}, 0.01, "opus")
        assert not any("offset/limit" in t for t in tips)

    def test_agent_spawn_tip(self):
        tips = generate_tips("Agent", {"prompt": "search"}, 0.05, "opus")
        assert any("Agent spawns" in t for t in tips)

    def test_large_write_tip(self):
        content = "\n".join(f"line {i}" for i in range(250))
        tips = generate_tips("Write", {"content": content}, 0.01, "opus")
        assert any("Edit" in t for t in tips)

    def test_haiku_tip_for_trivial_on_opus(self):
        # Trivial op (ls) on expensive Opus → recommend Haiku
        tips = generate_tips("Bash", {"command": "ls"}, 0.02, "opus")
        assert any("haiku" in t.lower() for t in tips)

    def test_haiku_tip_for_trivial_on_sonnet(self):
        # Trivial op (ls) on Sonnet → still recommend Haiku
        tips = generate_tips("Bash", {"command": "ls"}, 0.001, "sonnet")
        assert any("haiku" in t.lower() for t in tips)

    def test_no_tip_for_routine_on_opus(self):
        # Routine coding (Edit) on Opus → no tip (coach handles this, avoid duplication)
        tips = generate_tips("Edit", {"file_path": "/tmp/f.py", "old_string": "x", "new_string": "y"}, 0.02, "opus")
        assert not any("haiku" in t.lower() or "sonnet" in t.lower() for t in tips)

    def test_upgrade_tip_for_complex_on_haiku(self):
        # Agent spawn on Haiku → recommend Sonnet
        tips = generate_tips("Agent", {"prompt": "do something"}, 0.05, "haiku")
        assert any("sonnet" in t.lower() for t in tips)

    def test_opus_tip_for_complex_on_sonnet(self):
        # Agent spawn on Sonnet → recommend Opus
        tips = generate_tips("Agent", {"prompt": "do something"}, 0.05, "sonnet")
        assert any("opus" in t.lower() for t in tips)

    def test_no_tip_on_right_model(self):
        # Agent spawn on Opus → no model tip (Opus is correct for complex tasks)
        tips = generate_tips("Agent", {"prompt": "do something"}, 0.05, "opus")
        assert not any("/model" in t for t in tips)

    def test_full_test_tip(self):
        tips = generate_tips("Bash", {"command": "pytest"}, 0.01, "opus")
        assert any("relevant test files" in t for t in tips)

    def test_targeted_test_no_tip(self):
        tips = generate_tips("Bash", {"command": "pytest tests/test_cost.py"}, 0.01, "opus")
        assert not any("relevant test files" in t for t in tips)


class TestCostFormat:
    def test_sub_cent(self):
        assert format_cost(0.003) == "~$0.003"

    def test_very_small(self):
        assert format_cost(0.0001) == "~$0.001"

    def test_cents(self):
        assert format_cost(0.05) == "~$0.05"

    def test_dollars(self):
        assert format_cost(1.23) == "~$1.23"

    def test_token_format_small(self):
        assert format_tokens(500) == "500"

    def test_token_format_large(self):
        assert format_tokens(1500) == "1K"

    def test_token_format_very_large(self):
        assert format_tokens(12000) == "12K"
