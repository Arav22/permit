#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.claude/plugins/permit"
SETTINGS="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  permit installer"
echo "  ================"
echo ""

# Check Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "  Error: python3 is required but not found."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo "  Error: Python 3.10+ required, found $PY_VERSION"
    exit 1
fi

echo "  Python $PY_VERSION -- OK"

# Copy files
echo "  Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/core" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/hooks" "$INSTALL_DIR/"
echo "  Files copied."

# Ensure settings dir exists
mkdir -p "$HOME/.claude"

# Patch settings.json with Python (safe JSON handling)
python3 << 'PYEOF'
import json
import os
import sys

settings_path = os.path.expanduser("~/.claude/settings.json")
install_dir = os.path.expanduser("~/.claude/plugins/permit")

pre_cmd = f"python3 {install_dir}/hooks/pretooluse.py"
post_cmd = f"python3 {install_dir}/hooks/posttooluse.py"

if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)
else:
    settings = {}

hooks = settings.setdefault("hooks", {})

def find_permit_hook(hook_list):
    for entry in hook_list:
        for h in entry.get("hooks", []):
            if "permit" in h.get("command", ""):
                return h
    return None

def add_or_update(hook_list, cmd):
    existing = find_permit_hook(hook_list)
    if existing:
        existing["command"] = cmd
        return "updated"
    else:
        hook_list.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": cmd, "timeout": 5}]
        })
        return "added"

pre_list = hooks.setdefault("PreToolUse", [])
pre_status = add_or_update(pre_list, pre_cmd)

post_list = hooks.setdefault("PostToolUse", [])
post_status = add_or_update(post_list, post_cmd)

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")

print(f"  PreToolUse hook {pre_status}")
print(f"  PostToolUse hook {post_status}")
print(f"  Settings written to {settings_path}")
PYEOF

echo ""
echo "  Done! permit v3 is now active."
echo "  Features: permission explainer + cost estimation + smart rollback + coach"
echo "  Restart Claude Code to see it in action."
echo "  Use /permit-rollback to undo file changes."
echo ""
