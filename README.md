# permit

**Plain-English permission explainer for Claude Code.**

When Claude Code asks for permission to run a tool, `permit` tells you:
- **What** the command does
- **Why** Claude is asking
- **How** it connects to other operations in the session
- Whether it's **safe** or needs careful review

Works as a Claude Code plugin via PreToolUse hooks. No configuration needed — install and it starts explaining.

## Features

- **Instant explanations** — every permission prompt gets a plain-English breakdown
- **Safety ratings** — color-coded risk levels (safe / caution / danger)
- **Connection tracking** — shows how operations relate (e.g., "this edit follows the read of the same file")
- **Dependency diagrams** — when multiple tools fire in sequence, shows the chain
- **Command breakdown** — for bash commands, explains each flag and argument
- **File operation context** — for edits/writes, explains what's changing and why it matters
- **History awareness** — tracks what's been approved/denied to give context on repeated patterns

## Install

### From Plugin Marketplace

```
/install-plugin permit
```

### Manual Install

Copy this directory to your Claude Code plugins:

```bash
cp -r permit ~/.claude/plugins/local/permit
```

Then add to your settings:

```json
{
  "plugins": ["local/permit"]
}
```

## How It Works

`permit` registers a PreToolUse hook that intercepts every tool call before it reaches the permission dialog. It:

1. **Parses** the tool name and input (command, file path, edit content, etc.)
2. **Analyzes** the operation — what it does, what it touches, what could go wrong
3. **Checks history** — has this file/command been seen before in this session?
4. **Rates risk** — safe (read-only, familiar), caution (writes, new files), danger (destructive, network, secrets)
5. **Formats** a concise explanation shown alongside the permission prompt

## What You See

When Claude asks to run `git push origin main --force`:

```
┌─ permit ──────────────────────────────────────────┐
│ ⚠️  CAUTION — Destructive git operation            │
│                                                    │
│ Force-pushes your local main branch to remote,     │
│ overwriting any commits on origin that aren't       │
│ in your local history.                             │
│                                                    │
│ Risk: Teammates' unpulled commits will be lost.    │
│ Scope: Affects remote repository (visible to all). │
│                                                    │
│ 🔗 Related: You ran `git commit` 2 steps ago       │
│    └─ commit → push (deploying what you committed) │
└────────────────────────────────────────────────────┘
```

When Claude asks to edit `src/config.ts`:

```
┌─ permit ──────────────────────────────────────────┐
│ ✅ SAFE — File edit                                │
│                                                    │
│ Modifying src/config.ts: replacing a database      │
│ connection string with a new value.                │
│                                                    │
│ Scope: Local file only. Reversible with git.       │
│                                                    │
│ 🔗 Related: Claude read this file 1 step ago       │
│    └─ read → edit (modifying what it just read)    │
└────────────────────────────────────────────────────┘
```

## Configuration

Optional settings in `.claude/permit.config.json`:

```json
{
  "verbosity": "normal",
  "showDiagram": true,
  "showHistory": true,
  "riskThreshold": "all"
}
```

| Setting | Values | Default | Description |
|---------|--------|---------|-------------|
| `verbosity` | `"minimal"`, `"normal"`, `"detailed"` | `"normal"` | How much detail to show |
| `showDiagram` | `true`, `false` | `true` | Show connection diagrams |
| `showHistory` | `true`, `false` | `true` | Show related previous operations |
| `riskThreshold` | `"all"`, `"caution"`, `"danger"` | `"all"` | Only show for this risk level and above |

## License

MIT
