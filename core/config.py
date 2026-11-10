"""Load permit configuration from .claude/permit.config.json."""

import json
import os
from dataclasses import dataclass, field


@dataclass
class CostConfig:
    enabled: bool = True
    model: str = "opus"
    show_per_operation: bool = True
    show_session_total: bool = True
    show_tips: bool = True
    budget_usd: float = 0.0


@dataclass
class CoachConfig:
    enabled: bool = True
    max_tips_per_box: int = 2


@dataclass
class RollbackConfig:
    enabled: bool = True
    snapshot_threshold: str = "all"
    max_age_days: int = 7
    max_size_mb: int = 100
    max_file_size_bytes: int = 1_048_576
    auto_cleanup: bool = True


@dataclass
class PermitConfig:
    verbosity: str = "smart"
    show_diagram: bool = True
    show_history: bool = True
    risk_threshold: str = "all"
    cost: CostConfig = field(default_factory=CostConfig)
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
    coach: CoachConfig = field(default_factory=CoachConfig)


def _parse_cost(data: dict) -> CostConfig:
    c = CostConfig()
    if "enabled" in data:
        c.enabled = data["enabled"]
    if "model" in data:
        c.model = data["model"]
    if "showPerOperation" in data:
        c.show_per_operation = data["showPerOperation"]
    if "showSessionTotal" in data:
        c.show_session_total = data["showSessionTotal"]
    if "showTips" in data:
        c.show_tips = data["showTips"]
    if "budget" in data:
        c.budget_usd = float(data["budget"])
    return c


def _parse_coach(data: dict) -> CoachConfig:
    c = CoachConfig()
    if "enabled" in data:
        c.enabled = data["enabled"]
    if "maxTipsPerBox" in data:
        c.max_tips_per_box = data["maxTipsPerBox"]
    return c


def _parse_rollback(data: dict) -> RollbackConfig:
    r = RollbackConfig()
    if "enabled" in data:
        r.enabled = data["enabled"]
    if "snapshotThreshold" in data:
        r.snapshot_threshold = data["snapshotThreshold"]
    if "maxAgeDays" in data:
        r.max_age_days = data["maxAgeDays"]
    if "maxSizeMB" in data:
        r.max_size_mb = data["maxSizeMB"]
    if "maxFileSizeBytes" in data:
        r.max_file_size_bytes = data["maxFileSizeBytes"]
    if "autoCleanup" in data:
        r.auto_cleanup = data["autoCleanup"]
    return r


def load_config() -> PermitConfig:
    """Load config from .claude/permit.config.json or use defaults."""
    config = PermitConfig()

    search_paths = [
        os.path.join(os.getcwd(), ".claude", "permit.config.json"),
        os.path.join(os.path.expanduser("~"), ".claude", "permit.config.json"),
    ]

    for path in search_paths:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if "verbosity" in data:
                    config.verbosity = data["verbosity"]
                if "showDiagram" in data:
                    config.show_diagram = data["showDiagram"]
                if "showHistory" in data:
                    config.show_history = data["showHistory"]
                if "riskThreshold" in data:
                    config.risk_threshold = data["riskThreshold"]
                if "cost" in data and isinstance(data["cost"], dict):
                    config.cost = _parse_cost(data["cost"])
                if "rollback" in data and isinstance(data["rollback"], dict):
                    config.rollback = _parse_rollback(data["rollback"])
                if "coach" in data and isinstance(data["coach"], dict):
                    config.coach = _parse_coach(data["coach"])
                return config
        except (FileNotFoundError, json.JSONDecodeError):
            continue

    return config


def should_show(config: PermitConfig, risk: str) -> bool:
    """Check if we should show explanation for this risk level."""
    levels = {"all": 0, "caution": 1, "danger": 2}
    risk_values = {"safe": 0, "caution": 1, "danger": 2}

    threshold = levels.get(config.risk_threshold, 0)
    risk_val = risk_values.get(risk, 0)

    return risk_val >= threshold


def should_snapshot(config: PermitConfig, risk: str) -> bool:
    """Check if we should snapshot for this risk level."""
    if not config.rollback.enabled:
        return False
    levels = {"all": 0, "caution": 1, "danger": 2}
    risk_values = {"safe": 0, "caution": 1, "danger": 2}
    threshold = levels.get(config.rollback.snapshot_threshold, 0)
    risk_val = risk_values.get(risk, 0)
    return risk_val >= threshold
