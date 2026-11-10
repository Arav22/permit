# permit

**Every AI coding tool asks for permissions. None explain what they mean.**

When Claude Code says *"Claude wants to run `git push origin main --force`"* — do you know what that actually does? What about `kubectl apply -f deployment.yaml` or `sed -i 's/foo/bar/' config.py`?

**permit** translates every permission prompt into plain English. It tells you what's happening, why it matters, how risky it is, and how it connects to what Claude did before.

## Before vs After

**Without permit** — you see this:
```
Claude wants to run: sed -i '' 's/DB_HOST=localhost/DB_HOST=prod.db.internal/' .env
  Allow?  [y/n]
```

**With permit** — you see this:
```
+-permit-----------------------------------------------------------+
| CAUTION sed -i '' 's/DB_HOST=localhost/DB_HOS...                 |
|   Edits files in-place                                           |
|                                                                  |
| !! Touches sensitive path: Environment file -- likely contain... |
|                                                                  |
| Scope: Modifies local files. Reversible with git if tracked. ... |
|                                                                  |
| Recent:                                                          |
|   |- Read -- .env (12s ago)                                      |
|   '- sed -i '' 's/DB_HOST=localhost/DB_HOS... (now)              |
+-------------------------------------------------------------------+
```

Now you know: it's an in-place edit of your `.env` file, it likely contains secrets, and Claude just read it 12 seconds ago.

### More examples

**Dangerous compound command:**
```
+-permit-----------------------------------------------------------+
| DANGER rm -rf, then npm install                                  |
|   Runs 2 commands in order.                                      |
|                                                                  |
|   -> rm -rf: Force-deletes files without confirmation            |
|   -> && npm install: Installs npm packages -- runs install sc... |
|                                                                  |
| Scope: Modifies system or project dependencies. [System-wide]    |
+-------------------------------------------------------------------+
```

**Pipeline:**
```
+-permit-----------------------------------------------------------+
| CAUTION curl | jq | head                                         |
|   Pipes output through 3 commands.                               |
|                                                                  |
|   -> curl: Makes a network request                               |
|   -> jq: Processes JSON data                                     |
|   -> head: Shows the first lines of a file                       |
|                                                                  |
| Scope: Affects remote systems -- visible to others. [Remote /... |
+-------------------------------------------------------------------+
```

**Safe read-only:**
```
+-permit-----------------------------------------------------------+
| SAFE ls -la                                                      |
|   Lists directory contents                                       |
|                                                                  |
| Scope: Local only. No changes made.                              |
+-------------------------------------------------------------------+
```

## Features

- **Risk ratings** — every tool call is classified as safe (green), caution (yellow), or danger (red)
- **Pipe & chain parsing** — `cat file | grep err | wc -l` is broken into 3 stages, each explained
- **Workflow detection** — recognizes patterns like "explore -> modify", "test -> fix -> test", "stage -> commit -> push" and tells you which step you're on
- **Blast radius** — tells you if an action is local-only, project-wide, system-wide, or remote/visible-to-others
- **Sensitive path alerts** — warns when commands touch `.env`, SSH keys, credentials, CI configs, or cloud configs
- **Session memory** — tracks what Claude has done this session, shows connections between operations
- **File heat** — flags files that have been touched multiple times ("Touched 5x this session")
- **Content analysis** — for edits, detects changes to imports, function signatures, config values, and env vars
- **100+ command patterns** — recognizes git, docker, kubectl, terraform, aws, gcloud, npm, pip, cargo, go, make, and more
- **Zero config** — install and it works. Optional config if you want to tune verbosity or filtering

## Install

**One command:**

```bash
git clone https://github.com/Arav22/permit.git && bash permit/install.sh
```

This copies the plugin to `~/.claude/plugins/permit` and adds the hooks to your Claude Code settings. Restart Claude Code and you're done.

To uninstall: `bash permit/uninstall.sh`

### Manual install

If you prefer to set it up yourself, add these hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/plugins/permit/hooks/pretooluse.py",
        "timeout": 5
      }]
    }],
    "PostToolUse": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/plugins/permit/hooks/posttooluse.py",
        "timeout": 5
      }]
    }]
  }
}
```

### Requirements

- Python 3.10+
- No external dependencies (stdlib only)

### Demo

See what permit looks like before installing:

```bash
python3 demo.py
```

## How It Works

permit runs as a pair of Claude Code hooks:

1. **PreToolUse** — fires before every tool call. Analyzes the tool name and input, checks session history for context, detects workflow patterns, and outputs a formatted explanation as a system message.

2. **PostToolUse** — fires after every tool call. Records what happened in session history so future explanations can show connections.

### Architecture

```
hooks/
  pretooluse.py      entry point for PreToolUse hook
  posttooluse.py     entry point for PostToolUse hook

core/
  analyzer.py        classifies tools, parses bash commands, detects risk
  patterns.py        workflow pattern recognition (explore, modify, test-fix, deploy)
  tracker.py         session history with file heat tracking
  formatter.py       ASCII box output with ANSI colors
  config.py          optional user configuration
```

### What gets analyzed

| Tool | What permit checks |
|------|-------------------|
| **Bash** | Command classification, pipe chains, redirects, compound commands, sensitive paths, scope |
| **Edit** | Import/export changes, function signatures, config values, env vars, file sensitivity |
| **Write** | New vs overwrite, CI/build config detection, sensitive paths |
| **Read** | Sensitive file access (credentials, keys, configs) |
| **Agent** | Sub-agent description and scope |
| **WebFetch** | Domain extraction, network scope |
| **Workflow** | Multi-agent spawn warning |
| **Others** | Generic tool identification with review prompt |

## Configuration

Optional — create `.claude/permit.config.json` in your project or home directory:

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
| `verbosity` | `minimal`, `normal`, `detailed` | `normal` | How much detail to show |
| `showDiagram` | `true`, `false` | `true` | Show operation chain diagrams |
| `showHistory` | `true`, `false` | `true` | Show related previous operations |
| `riskThreshold` | `all`, `caution`, `danger` | `all` | Only show for this risk level and above |

Set `riskThreshold` to `caution` if you don't want explanations for safe/read-only operations.

## Development

```bash
# Run tests
pytest -v

# Run a specific test file
pytest tests/test_analyzer.py -v

# Test a hook manually
echo '{"tool_name": "Bash", "tool_input": {"command": "git push --force"}}' | python3 hooks/pretooluse.py
```

## Why this exists

AI coding assistants ask for dozens of permissions per session. Most users either:
- **Approve everything** because they don't understand the prompts
- **Deny everything** because they're cautious but can't evaluate the risk
- **Slow down** to manually parse each command, breaking their flow

permit gives you the context to make fast, informed decisions. It's the missing UX layer between AI tools and the humans who approve them.

## License

MIT
