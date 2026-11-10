"""Tests for the hints catalog loading and obsolescence detection."""

import json
import os
import pytest
from unittest.mock import patch
from core.discovery import _load_catalog, detect_hints, Hint


class TestLoadCatalog:
    def test_loads_bundled_catalog(self):
        catalog = _load_catalog()
        assert len(catalog["hints"]) >= 10
        assert any(h["id"] == "hint_compact" for h in catalog["hints"])

    def test_catalog_has_obsolete_patterns(self):
        catalog = _load_catalog()
        assert len(catalog["obsolete_patterns"]) >= 1

    def test_user_override_merges(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.discovery._USER_CATALOG_PATH",
                            str(tmp_path / "permit-hints.json"))
        custom = {
            "version": "test",
            "hints": [{"id": "hint_custom", "one_liner": "/custom-command -- test hint"}],
            "obsolete_patterns": []
        }
        (tmp_path / "permit-hints.json").write_text(json.dumps(custom))
        catalog = _load_catalog()
        ids = [h["id"] for h in catalog["hints"]]
        assert "hint_compact" in ids   # bundled still present
        assert "hint_custom" in ids    # user addition merged in

    def test_user_override_replaces_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.discovery._USER_CATALOG_PATH",
                            str(tmp_path / "permit-hints.json"))
        override = {
            "version": "test",
            "hints": [{"id": "hint_compact", "one_liner": "/compact -- OVERRIDDEN"}],
            "obsolete_patterns": []
        }
        (tmp_path / "permit-hints.json").write_text(json.dumps(override))
        catalog = _load_catalog()
        compact = next(h for h in catalog["hints"] if h["id"] == "hint_compact")
        assert compact["one_liner"] == "/compact -- OVERRIDDEN"

    def test_missing_user_file_handled_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.discovery._USER_CATALOG_PATH",
                            str(tmp_path / "nonexistent.json"))
        catalog = _load_catalog()
        assert len(catalog["hints"]) >= 10  # bundled catalog still loads

    def test_invalid_user_json_handled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.discovery._USER_CATALOG_PATH",
                            str(tmp_path / "permit-hints.json"))
        (tmp_path / "permit-hints.json").write_text("not json {{{")
        catalog = _load_catalog()
        assert len(catalog["hints"]) >= 10


class TestObsolescenceDetection:
    def test_obs_model_env_fires(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints(
                "Bash",
                {"command": "export ANTHROPIC_MODEL=claude-opus-4"},
                [],
                False,
                str(tmp_path)
            )
        assert len(hints) == 1
        assert hints[0].is_obsolete is True
        assert "OBS:" in hints[0].one_liner
        assert "/model" in hints[0].one_liner

    def test_obs_settings_cat_fires(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints(
                "Bash",
                {"command": "cat ~/.claude/settings.json"},
                [],
                False,
                str(tmp_path)
            )
        assert len(hints) == 1
        assert hints[0].is_obsolete is True

    def test_obsolete_takes_priority_over_discovery(self, tmp_path):
        # Even with n==0 (hint_resume eligible), obs wins because it's inserted first
        with patch("core.discovery._hint_seen_count", return_value=0), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints(
                "Bash",
                {"command": "export ANTHROPIC_MODEL=opus"},
                [],
                False,
                str(tmp_path)
            )
        assert hints[0].is_obsolete is True

    def test_obs_suppressed_after_3_appearances(self, tmp_path):
        with patch("core.discovery._hint_seen_count", return_value=3), \
             patch("core.discovery._record_hint"), \
             patch("core.discovery.load_project_data", return_value={"sessions": []}), \
             patch("core.discovery.get_session_cost", return_value=0):
            hints = detect_hints(
                "Bash",
                {"command": "export ANTHROPIC_MODEL=opus"},
                [],
                False,
                str(tmp_path)
            )
        # obs_model_env suppressed, falls through to hint_resume
        assert len(hints) <= 1
        if hints:
            assert not hints[0].is_obsolete  # regular hint, not obsolete
