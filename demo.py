#!/usr/bin/env python3
"""Generate demo output for terminal screenshots."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import analyze_bash, analyze_edit, analyze_read
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
    print("\n  permit demo -- what you see when Claude asks for permissions\n")
    for label, cmd in DEMOS:
        analysis = analyze_bash(cmd)
        box = format_explanation(analysis)
        print(f"  \033[2m$ {cmd}\033[0m")
        print(box)
        print()
    print("  Run with: python3 demo.py")
    print("  Install with: bash install.sh")
    print()


if __name__ == "__main__":
    main()
