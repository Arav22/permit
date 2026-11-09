"""Tool call analyzer — classifies risk and generates plain-English explanations."""

import re
import shlex
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Analysis:
    risk: str  # "safe", "caution", "danger"
    icon: str
    title: str
    explanation: str
    scope: str
    warnings: list = field(default_factory=list)


DANGEROUS_COMMANDS = {
    r"rm\s+-rf": "Recursively deletes files/directories without confirmation",
    r"rm\s+-r": "Recursively deletes files/directories",
    r"git\s+push\s+.*--force": "Force-pushes to remote, overwriting history others may depend on",
    r"git\s+push\s+-f": "Force-pushes to remote, overwriting history others may depend on",
    r"git\s+reset\s+--hard": "Discards all uncommitted changes permanently",
    r"git\s+clean\s+-f": "Deletes untracked files permanently",
    r"git\s+checkout\s+--\s": "Discards uncommitted changes to specified files",
    r"git\s+branch\s+-D": "Force-deletes a branch even if not fully merged",
    r"chmod\s+777": "Makes files world-readable/writable/executable",
    r"curl\s+.*\|\s*sh": "Downloads and executes remote code — high risk",
    r"curl\s+.*\|\s*bash": "Downloads and executes remote code — high risk",
    r"wget\s+.*\|\s*sh": "Downloads and executes remote code — high risk",
    r"dd\s+if=": "Low-level disk copy — can overwrite entire drives",
    r"mkfs": "Creates a filesystem — destroys existing data on device",
    r">\s*/dev/sd": "Writes directly to a disk device",
    r"kill\s+-9": "Force-kills a process without allowing cleanup",
    r"pkill\s+-9": "Force-kills processes by name without cleanup",
    r"DROP\s+TABLE": "Deletes an entire database table",
    r"DROP\s+DATABASE": "Deletes an entire database",
    r"TRUNCATE\s+TABLE": "Removes all rows from a table",
    r"DELETE\s+FROM\s+\w+\s*$": "Deletes all rows from a table (no WHERE clause)",
}

CAUTION_COMMANDS = {
    r"npm\s+install": "Installs packages from npm — runs install scripts that can execute arbitrary code",
    r"pip\s+install": "Installs Python packages — may run setup.py with arbitrary code",
    r"brew\s+install": "Installs a Homebrew package",
    r"apt\s+install": "Installs a system package",
    r"git\s+push": "Pushes commits to remote repository (visible to collaborators)",
    r"git\s+merge": "Merges branches — may create conflicts or change history",
    r"git\s+rebase": "Rewrites commit history — can complicate collaboration",
    r"git\s+stash\s+drop": "Permanently discards a stash entry",
    r"docker\s+run": "Runs a container — may expose ports or mount volumes",
    r"ssh\s+": "Opens a remote connection",
    r"scp\s+": "Copies files to/from a remote host",
    r"curl\s+": "Makes a network request",
    r"wget\s+": "Downloads from a URL",
    r"mv\s+": "Moves/renames files — original location no longer exists",
    r"cp\s+-r": "Recursively copies files — may overwrite at destination",
    r"chmod\s+": "Changes file permissions",
    r"chown\s+": "Changes file ownership",
    r"sed\s+-i": "Edits files in-place (no backup by default on Linux)",
    r"env\s+": "Runs command with modified environment",
    r"export\s+": "Sets environment variables for the session",
}

SAFE_COMMANDS = {
    r"^ls\b": "Lists directory contents",
    r"^cat\b": "Displays file contents",
    r"^head\b": "Shows the first lines of a file",
    r"^tail\b": "Shows the last lines of a file",
    r"^echo\b": "Prints text to the terminal",
    r"^pwd\b": "Shows the current directory path",
    r"^whoami\b": "Shows the current user",
    r"^date\b": "Shows the current date/time",
    r"^wc\b": "Counts lines/words/characters",
    r"^grep\b": "Searches text using patterns",
    r"^find\b": "Searches for files by name/attributes",
    r"^which\b": "Shows the path of a command",
    r"^git\s+status": "Shows which files have changed",
    r"^git\s+log": "Shows commit history",
    r"^git\s+diff": "Shows changes between commits/files",
    r"^git\s+branch\b(?!\s+-D)": "Lists or creates branches",
    r"^git\s+show": "Shows a specific commit",
    r"^git\s+blame": "Shows who last modified each line",
    r"^git\s+remote\s+-v": "Lists remote repositories",
    r"^python3?\s+-c": "Runs a Python one-liner",
    r"^node\s+-e": "Runs a JavaScript one-liner",
    r"^jq\b": "Processes JSON data",
    r"^tree\b": "Shows directory structure",
    r"^du\b": "Shows disk usage",
    r"^df\b": "Shows disk space",
    r"^uname\b": "Shows system information",
    r"^file\b": "Identifies file type",
    r"^stat\b": "Shows file metadata",
    r"^gh\s+(issue|pr)\s+(list|view|status)": "Views GitHub issues/PRs (read-only)",
    r"^gh\s+api\s+": "Makes a GitHub API request",
}

SENSITIVE_PATHS = [
    (r"\.env", "Environment file — may contain secrets/API keys"),
    (r"credentials", "Credentials file — may contain passwords or tokens"),
    (r"\.ssh/", "SSH directory — contains private keys"),
    (r"\.aws/", "AWS config — contains access keys"),
    (r"\.git/config", "Git config — may contain auth tokens"),
    (r"id_rsa", "SSH private key"),
    (r"\.pem$", "Certificate/key file"),
    (r"secret", "File with 'secret' in name — review contents carefully"),
    (r"password", "File with 'password' in name — review contents carefully"),
    (r"token", "File with 'token' in name — may contain auth tokens"),
]


def analyze_bash(command: str) -> Analysis:
    """Analyze a bash command and return a human-readable explanation."""
    cmd = command.strip()

    for pattern, desc in DANGEROUS_COMMANDS.items():
        if re.search(pattern, cmd, re.IGNORECASE):
            return Analysis(
                risk="danger",
                icon="⛔",
                title="Destructive operation",
                explanation=desc,
                scope=_bash_scope(cmd),
                warnings=_check_sensitive_paths_in_cmd(cmd),
            )

    for pattern, desc in CAUTION_COMMANDS.items():
        if re.search(pattern, cmd, re.IGNORECASE):
            return Analysis(
                risk="caution",
                icon="⚠️",
                title="Review carefully",
                explanation=desc,
                scope=_bash_scope(cmd),
                warnings=_check_sensitive_paths_in_cmd(cmd),
            )

    for pattern, desc in SAFE_COMMANDS.items():
        if re.search(pattern, cmd, re.IGNORECASE):
            return Analysis(
                risk="safe",
                icon="✅",
                title="Read-only / informational",
                explanation=desc,
                scope="Local only. No changes made.",
            )

    return Analysis(
        risk="caution",
        icon="❓",
        title="Unknown command",
        explanation=_describe_command(cmd),
        scope=_bash_scope(cmd),
        warnings=_check_sensitive_paths_in_cmd(cmd),
    )


def analyze_edit(file_path: str, old_string: str, new_string: str) -> Analysis:
    """Analyze a file edit operation."""
    warnings = _check_sensitive_paths(file_path)

    if not old_string and new_string:
        action = "Inserting new content"
    elif old_string and not new_string:
        action = "Deleting content"
    else:
        action = "Replacing content"

    old_lines = old_string.count("\n") + 1 if old_string else 0
    new_lines = new_string.count("\n") + 1 if new_string else 0
    size_note = f"Changing {old_lines} line(s) to {new_lines} line(s)"

    return Analysis(
        risk="danger" if warnings else "caution",
        icon="⛔" if warnings else "✏️",
        title=f"File edit — {_shorten_path(file_path)}",
        explanation=f"{action} in {_shorten_path(file_path)}. {size_note}.",
        scope="Local file only. Reversible with git checkout or undo.",
        warnings=warnings,
    )


def analyze_write(file_path: str, content: str) -> Analysis:
    """Analyze a file write (create/overwrite) operation."""
    import os

    warnings = _check_sensitive_paths(file_path)
    exists = os.path.exists(file_path)

    if exists:
        action = "Overwriting existing file"
        risk = "caution"
    else:
        action = "Creating new file"
        risk = "safe"

    if warnings:
        risk = "danger"

    lines = content.count("\n") + 1
    icon_map = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}

    return Analysis(
        risk=risk,
        icon=icon_map[risk],
        title=f"{'Overwrite' if exists else 'Create'} — {_shorten_path(file_path)}",
        explanation=f"{action}: {_shorten_path(file_path)} ({lines} lines).",
        scope="Local file only." + (" Overwrites existing content!" if exists else ""),
        warnings=warnings,
    )


def analyze_read(file_path: str) -> Analysis:
    """Analyze a file read operation."""
    warnings = _check_sensitive_paths(file_path)
    return Analysis(
        risk="caution" if warnings else "safe",
        icon="⚠️" if warnings else "📄",
        title=f"Read — {_shorten_path(file_path)}",
        explanation=f"Reading contents of {_shorten_path(file_path)}.",
        scope="Read-only. No changes made.",
        warnings=warnings,
    )


def analyze_tool(tool_name: str, tool_input: dict) -> Optional[Analysis]:
    """Analyze any tool call and return an explanation."""
    if tool_name == "Bash":
        return analyze_bash(tool_input.get("command", ""))
    elif tool_name == "Edit":
        return analyze_edit(
            tool_input.get("file_path", ""),
            tool_input.get("old_string", ""),
            tool_input.get("new_string", ""),
        )
    elif tool_name == "Write":
        return analyze_write(
            tool_input.get("file_path", ""),
            tool_input.get("content", ""),
        )
    elif tool_name == "Read":
        return analyze_read(tool_input.get("file_path", ""))
    elif tool_name == "Agent":
        return Analysis(
            risk="safe",
            icon="🤖",
            title="Launching sub-agent",
            explanation=f"Spawning a background agent: {tool_input.get('description', 'unknown task')}.",
            scope="Runs in a sandboxed context. Will ask its own permissions.",
        )
    elif tool_name == "WebFetch":
        return Analysis(
            risk="caution",
            icon="🌐",
            title="Fetching web content",
            explanation=f"Downloading content from a URL.",
            scope="Network request. Sends your IP to the target server.",
        )
    elif tool_name in ("Grep", "Glob", "Search"):
        return Analysis(
            risk="safe",
            icon="🔍",
            title=f"Searching files ({tool_name})",
            explanation="Searching the codebase for patterns or files.",
            scope="Read-only. No changes made.",
        )
    else:
        return Analysis(
            risk="caution",
            icon="❓",
            title=f"Tool: {tool_name}",
            explanation=f"Claude wants to use the {tool_name} tool.",
            scope="Review the parameters before approving.",
        )


def _describe_command(cmd: str) -> str:
    """Best-effort description of an unknown command."""
    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()
    if not parts:
        return "Empty command"
    binary = parts[0].split("/")[-1]
    return f"Runs `{binary}` — not in the known-safe list, review the full command."


def _bash_scope(cmd: str) -> str:
    """Determine the scope of a bash command."""
    if re.search(r"git\s+push|curl|wget|ssh|scp|gh\s+pr\s+create|gh\s+issue\s+create", cmd):
        return "Affects remote systems (network/git remote). Visible to others."
    if re.search(r"rm|mv|cp|chmod|chown|sed\s+-i|tee|>", cmd):
        return "Modifies local files. Reversible with git if tracked."
    return "Local only."


def _check_sensitive_paths(path: str) -> list:
    """Check if a file path looks sensitive."""
    warnings = []
    for pattern, desc in SENSITIVE_PATHS:
        if re.search(pattern, path, re.IGNORECASE):
            warnings.append(desc)
    return warnings


def _check_sensitive_paths_in_cmd(cmd: str) -> list:
    """Check if a command references sensitive paths."""
    warnings = []
    for pattern, desc in SENSITIVE_PATHS:
        if re.search(pattern, cmd, re.IGNORECASE):
            warnings.append(f"References sensitive path: {desc}")
    return warnings


def _shorten_path(path: str) -> str:
    """Shorten a file path for display."""
    import os

    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    parts = path.split("/")
    if len(parts) > 4:
        return "/".join(parts[:2]) + "/.../" + "/".join(parts[-2:])
    return path
