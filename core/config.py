"""Load permit configuration from .claude/permit.config.json."""

import json
import os
from dataclasses import dataclass


@dataclass
class PermitConfig:
    verbosity: str = "normal"
    show_diagram: bool = True
    show_history: bool = True
    risk_threshold: str = "all"


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
