"""Formats analysis results into box-drawing display for the permission prompt."""

from core.analyzer import Analysis


def format_explanation(analysis: Analysis, related_chain: str = "", verbosity: str = "normal") -> str:
    """Format an analysis into a bordered display string."""
    risk_labels = {
        "safe": "SAFE",
        "caution": "CAUTION",
        "danger": "DANGER",
    }

    risk_label = risk_labels.get(analysis.risk, "UNKNOWN")
    header = f"{analysis.icon}  {risk_label} — {analysis.title}"

    lines = [
        f"┌─ permit {'─' * max(1, 50 - len('permit') - 2)}┐",
        f"│ {header}",
        f"│",
        f"│ {analysis.explanation}",
    ]

    if verbosity != "minimal":
        lines.append(f"│")
        lines.append(f"│ Scope: {analysis.scope}")

    if analysis.warnings:
        lines.append(f"│")
        for w in analysis.warnings:
            lines.append(f"│ 🚨 {w}")

    if related_chain and verbosity != "minimal":
        lines.append(f"│")
        lines.append(f"│ 🔗 Operation chain:")
        for chain_line in related_chain.split("\n"):
            lines.append(f"│ {chain_line}")

    lines.append(f"└{'─' * 52}┘")

    return "\n".join(lines)


def format_compact(analysis: Analysis) -> str:
    """One-line compact format for minimal verbosity."""
    risk_labels = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}
    icon = risk_labels.get(analysis.risk, "❓")
    return f"{icon} {analysis.title}: {analysis.explanation}"
