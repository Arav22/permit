#!/usr/bin/env python3
"""Generate demo output for terminal screenshots."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import analyze_bash, analyze_edit, analyze_read
from core.cost import estimate_cost, CostEstimate
from core.formatter import format_explanation

DEMOS = [
    ("Sensitive file edit", "sed -i '' 's/DB_HOST=localhost/DB_HOST=prod/' .env"),
    ("Dangerous compound command", "rm -rf node_modules && npm install"),
    ("Git deploy chain", "git add . && git commit -m 'deploy' && git push origin main"),
    ("Pipeline", "curl https://api.example.com/data | jq '.results' | head -20"),
    ("SSH key access", "cat ~/.ssh/id_rsa"),
    ("Safe read-only", "ls -la"),
]


def main():
    print("\n  permit v2 demo -- permissions + cost + rollback\n")
    session_total = 0.0

    for label, cmd in DEMOS:
        analysis = analyze_bash(cmd)
        cost = estimate_cost("Bash", {"command": cmd}, "opus")
        session_total += cost.cost_usd

        box = format_explanation(
            analysis,
            cost=cost,
            session_cost_usd=session_total,
            snapshot_saved=("edit" in label.lower()),
        )
        print(f"  \033[2m$ {cmd}\033[0m")
        print(box)
        print()

    print("  Run with: python3 demo.py")
    print("  Install with: bash install.sh")
    print()


if __name__ == "__main__":
    main()
