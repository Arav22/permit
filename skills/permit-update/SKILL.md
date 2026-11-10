---
name: permit-update
description: Fetch the latest permit hints catalog from GitHub
argument-hint: []
allowed-tools: [Bash, Read, Write]
---

# permit-update — Refresh Hints Catalog

You are updating permit's hints catalog to pick up new Claude Code commands,
updated tips, and new obsolescence patterns.

## Steps

1. **Fetch the latest catalog:**
   ```bash
   curl -s https://raw.githubusercontent.com/Arav22/permit/main/core/hints_catalog.json
   ```

2. **Validate it's valid JSON** with a `version` field and `hints` array:
   ```bash
   python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d['version'], len(d['hints']), 'hints')"
   ```
   Pipe the curl output into this. If validation fails, tell the user and stop.

3. **Save to `~/.claude/permit-hints.json`:**
   Write the validated JSON to `~/.claude/permit-hints.json`.

4. **Report:**
   Tell the user:
   - New catalog version (e.g., "2026-11")
   - Number of hints
   - Number of obsolete patterns
   - "Catalog saved to ~/.claude/permit-hints.json"

## Notes

- The bundled `hints_catalog.json` inside the plugin is NOT overwritten — the user
  override file at `~/.claude/permit-hints.json` extends it
- If you want to add your own custom hints, edit `~/.claude/permit-hints.json` directly
- To revert to the bundled catalog, delete `~/.claude/permit-hints.json`
