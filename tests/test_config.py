"""Tests for configuration loading."""

import json
import pytest
from core.config import (
    load_config,
    should_show,
    should_snapshot,
    PermitConfig,
    CostConfig,
    RollbackConfig,
)


class TestDefaultConfig:
    def test_all_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        config = load_config()
        assert config.verbosity == "smart"
        assert config.show_diagram is True
        assert config.show_history is True
        assert config.risk_threshold == "all"
        assert config.cost.enabled is True
        assert config.cost.model == ""  # empty = auto-detect at runtime
        assert config.rollback.enabled is True
        assert config.rollback.snapshot_threshold == "all"
        assert config.rollback.max_age_days == 7
        assert config.rollback.max_size_mb == 100


class TestLoadWithCost:
    def test_cost_section(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".claude"
        cfg_dir.mkdir()
        (cfg_dir / "permit.config.json").write_text(json.dumps({
            "cost": {
                "enabled": False,
                "model": "sonnet",
                "showPerOperation": False,
                "showSessionTotal": True,
                "showTips": False,
            }
        }))
        config = load_config()
        assert config.cost.enabled is False
        assert config.cost.model == "sonnet"
        assert config.cost.show_per_operation is False
        assert config.cost.show_session_total is True
        assert config.cost.show_tips is False


class TestLoadWithRollback:
    def test_rollback_section(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".claude"
        cfg_dir.mkdir()
        (cfg_dir / "permit.config.json").write_text(json.dumps({
            "rollback": {
                "enabled": True,
                "snapshotThreshold": "caution",
                "maxAgeDays": 14,
                "maxSizeMB": 200,
                "maxFileSizeBytes": 2_097_152,
                "autoCleanup": False,
            }
        }))
        config = load_config()
        assert config.rollback.snapshot_threshold == "caution"
        assert config.rollback.max_age_days == 14
        assert config.rollback.max_size_mb == 200
        assert config.rollback.max_file_size_bytes == 2_097_152
        assert config.rollback.auto_cleanup is False


class TestPartialConfig:
    def test_only_verbosity(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".claude"
        cfg_dir.mkdir()
        (cfg_dir / "permit.config.json").write_text(json.dumps({
            "verbosity": "minimal"
        }))
        config = load_config()
        assert config.verbosity == "minimal"
        assert config.cost.enabled is True
        assert config.rollback.enabled is True

    def test_partial_cost(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg_dir = tmp_path / ".claude"
        cfg_dir.mkdir()
        (cfg_dir / "permit.config.json").write_text(json.dumps({
            "cost": {"model": "haiku"}
        }))
        config = load_config()
        assert config.cost.model == "haiku"
        assert config.cost.enabled is True
        assert config.cost.show_tips is True


class TestShouldShow:
    def test_all_threshold(self):
        config = PermitConfig(risk_threshold="all")
        assert should_show(config, "safe") is True
        assert should_show(config, "caution") is True
        assert should_show(config, "danger") is True

    def test_caution_threshold(self):
        config = PermitConfig(risk_threshold="caution")
        assert should_show(config, "safe") is False
        assert should_show(config, "caution") is True
        assert should_show(config, "danger") is True

    def test_danger_threshold(self):
        config = PermitConfig(risk_threshold="danger")
        assert should_show(config, "safe") is False
        assert should_show(config, "caution") is False
        assert should_show(config, "danger") is True


class TestShouldSnapshot:
    def test_disabled(self):
        config = PermitConfig()
        config.rollback.enabled = False
        assert should_snapshot(config, "caution") is False

    def test_all_threshold(self):
        config = PermitConfig()
        config.rollback.snapshot_threshold = "all"
        assert should_snapshot(config, "safe") is True
        assert should_snapshot(config, "caution") is True

    def test_caution_threshold(self):
        config = PermitConfig()
        config.rollback.snapshot_threshold = "caution"
        assert should_snapshot(config, "safe") is False
        assert should_snapshot(config, "caution") is True
        assert should_snapshot(config, "danger") is True
