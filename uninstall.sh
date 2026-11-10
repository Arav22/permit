#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.claude/plugins/permit"
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "  permit uninstaller"
echo "  =================="
echo ""

# Remove hooks from settings.json
if [ -f "$SETTINGS" ]; then
    python3 << 'PYEOF'
import json
import os

settings_path = os.path.expanduser("~/.claude/settings.json")

with open(settings_path) as f:
    settings = json.load(f)

hooks = settings.get("hooks", {})
removed = 0

for event in ["PreToolUse", "PostToolUse"]:
    if event in hooks:
        original = len(hooks[event])
        hooks[event] = [
            entry for entry in hooks[event]
            if not any("permit" in h.get("command", "") for h in entry.get("hooks", []))
        ]
        removed += original - len(hooks[event])
        if not hooks[event]:
            del hooks[event]

if not hooks:
    del settings["hooks"]

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print(f"  Removed {removed} hook(s) from settings.json")
PYEOF
else
    echo "  No settings.json found -- skipping"
fi

# Remove installed files
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  Removed $INSTALL_DIR"
else
    echo "  No installed files found -- skipping"
fi

echo ""
echo "  Done! permit has been removed."
echo "  Restart Claude Code for changes to take effect."
echo ""
