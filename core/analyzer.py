"""Tool call analyzer -- classifies risk and generates plain-English explanations.

Parses pipe chains, redirects, compound commands, and subcommands to give
users a genuine understanding of what Claude is about to do.
"""

import os
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
    blast_radius: str = "local"  # "local", "project", "system", "remote"
    warnings: list = field(default_factory=list)
    stages: list = field(default_factory=list)  # for pipe/chain breakdowns


# ---------------------------------------------------------------------------
# Bash command knowledge base
# ---------------------------------------------------------------------------

# Danger: destructive, irreversible, or remote-affecting commands
_DANGER = [
    (r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force)", "Force-deletes files without confirmation"),
    (r"rm\s+(-[a-zA-Z]*r[a-zA-Z]*)", "Recursively deletes files and directories"),
    (r"git\s+push\s+.*--force", "Force-pushes to remote -- overwrites history others depend on"),
    (r"git\s+push\s+.*-f\b", "Force-pushes to remote -- overwrites history others depend on"),
    (r"git\s+reset\s+--hard", "Discards all uncommitted changes permanently"),
    (r"git\s+clean\s+-[a-zA-Z]*f", "Deletes untracked files permanently"),
    (r"git\s+checkout\s+--\s", "Discards uncommitted changes to files"),
    (r"git\s+branch\s+-D\b", "Force-deletes a branch even if not merged"),
    (r"git\s+rebase\s+.*--force", "Rewrites shared history -- can break collaborators"),
    (r"chmod\s+777", "Makes files world-readable/writable/executable"),
    (r"chmod\s+-R\s+777", "Recursively makes everything world-accessible"),
    (r"curl\s+.*\|\s*(ba)?sh", "Downloads and executes remote code -- high risk"),
    (r"wget\s+.*\|\s*(ba)?sh", "Downloads and executes remote code -- high risk"),
    (r"\bdd\s+if=", "Low-level disk copy -- can overwrite entire drives"),
    (r"\bmkfs\b", "Creates filesystem -- destroys existing data on device"),
    (r">\s*/dev/sd", "Writes directly to a disk device"),
    (r"\bkill\s+-9\b", "Force-kills process without cleanup"),
    (r"\bpkill\s+-9\b", "Force-kills processes by name without cleanup"),
    (r"\bkillall\s+-9\b", "Force-kills all matching processes"),
    (r"DROP\s+(TABLE|DATABASE|INDEX)", "Drops database objects permanently"),
    (r"TRUNCATE\s+TABLE", "Removes all rows from a table"),
    (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "Deletes all rows -- no WHERE clause"),
    (r"terraform\s+destroy", "Destroys all managed infrastructure"),
    (r"kubectl\s+delete\s+(namespace|ns)\b", "Deletes an entire Kubernetes namespace"),
    (r"kubectl\s+delete\s+.*--all\b", "Deletes all resources of a type"),
    (r"docker\s+(system|volume)\s+prune", "Permanently removes unused Docker data"),
    (r"aws\s+.*\s+delete-", "Deletes an AWS resource"),
    (r"gcloud\s+.*\s+delete\b", "Deletes a Google Cloud resource"),
    (r"sudo\s+rm\b", "Deletes files with root privileges"),
    (r"npm\s+publish", "Publishes package to npm registry -- public and permanent"),
    (r"pip\s+upload", "Uploads package to PyPI -- public"),
    (r"docker\s+run\s+.*-v\s+/[^:]*:/", "Runs container with host filesystem mount -- full access to your files"),
]

# Caution: modifying, network, or side-effecting commands
_CAUTION = [
    # Test runners — execute code with potential side effects (network, files, DB)
    (r"pytest\b", "Runs the Python test suite -- executes all test code"),
    (r"python3?\s+-m\s+pytest", "Runs the Python test suite"),
    (r"^cargo\s+test\b", "Runs Rust test suite -- executes all test code"),
    (r"^go\s+test\b", "Runs Go test suite -- executes all test code"),
    (r"^npm\s+test\b", "Runs npm test script -- check package.json to see what it does"),
    (r"npm\s+install", "Installs npm packages -- runs install scripts that execute arbitrary code"),
    (r"npm\s+run\b", "Runs an npm script -- check package.json to see what it does"),
    (r"npx\s+", "Downloads and runs an npm package"),
    (r"yarn\s+(add|install)", "Installs packages via yarn"),
    (r"pnpm\s+(add|install)", "Installs packages via pnpm"),
    (r"pip\s+install", "Installs Python packages -- may run setup.py"),
    (r"pip\s+uninstall", "Removes installed Python packages"),
    (r"brew\s+install", "Installs a Homebrew package"),
    (r"brew\s+uninstall", "Removes a Homebrew package"),
    (r"apt(-get)?\s+install", "Installs system packages"),
    (r"git\s+push\b(?!.*--force)(?!.*-f\b)", "Pushes commits to remote -- visible to collaborators"),
    (r"git\s+merge\b", "Merges branches -- may cause conflicts"),
    (r"git\s+rebase\b(?!.*--force)", "Rewrites local commit history"),
    (r"git\s+stash\s+drop", "Permanently discards a stash entry"),
    (r"git\s+commit\b", "Creates a new commit from staged changes"),
    (r"git\s+add\b", "Stages files for the next commit"),
    (r"git\s+checkout\s+(?!--)(\S+)", "Switches branch or restores files"),
    (r"docker\s+run\b", "Runs a container -- may expose ports or mount host volumes"),
    (r"docker\s+compose\s+up", "Starts multi-container services"),
    (r"docker\s+compose\s+down", "Stops and removes containers, networks"),
    (r"docker\s+build\b", "Builds a container image"),
    (r"kubectl\s+apply\b", "Applies configuration to Kubernetes cluster"),
    (r"kubectl\s+create\b", "Creates Kubernetes resources"),
    (r"kubectl\s+delete\b(?!.*--all)(?!.*(namespace|ns))", "Deletes a Kubernetes resource"),
    (r"kubectl\s+exec\b", "Executes a command inside a running pod"),
    (r"kubectl\s+rollout\b", "Manages deployment rollouts"),
    (r"terraform\s+apply\b", "Applies infrastructure changes -- creates/modifies real resources"),
    (r"terraform\s+plan\b", "Plans infrastructure changes -- read-only but connects to cloud"),
    (r"aws\s+.*\s+(create-|put-|update-|start-|stop-)", "Modifies an AWS resource"),
    (r"gcloud\s+.*\s+(create|update)\b", "Modifies a Google Cloud resource"),
    (r"ssh\s+", "Opens a remote shell connection"),
    (r"scp\s+", "Copies files to/from a remote host"),
    (r"rsync\s+", "Syncs files -- can overwrite at destination"),
    (r"curl\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|-d\s)", "Makes a mutating HTTP request"),
    (r"curl\b(?!.*\|\s*(ba)?sh)", "Makes a network request"),
    (r"wget\b(?!.*\|\s*(ba)?sh)", "Downloads from a URL"),
    (r"\bmv\s+", "Moves/renames files -- originals no longer at old path"),
    (r"\bcp\s+(-[a-zA-Z]*r|--recursive)", "Recursively copies -- may overwrite destination"),
    (r"\bchmod\b(?!\s+777)", "Changes file permissions"),
    (r"\bchown\b", "Changes file ownership"),
    (r"\bsed\s+-i", "Edits files in-place"),
    (r"\bawk\s+-i", "Edits files in-place with awk"),
    (r"python3?\s+\S+\.py\b", "Runs a Python script -- review what it does"),
    (r"node\s+\S+\.js\b", "Runs a Node.js script -- review what it does"),
    (r"cargo\s+build\b", "Compiles a Rust project"),
    (r"cargo\s+run\b", "Builds and runs a Rust program"),
    (r"go\s+build\b", "Compiles a Go project"),
    (r"go\s+run\b", "Builds and runs a Go program"),
    (r"make\b(?!\s+-n)", "Runs Makefile targets -- review what they do"),
    (r"gh\s+pr\s+create", "Creates a pull request -- visible to collaborators"),
    (r"gh\s+issue\s+create", "Creates a GitHub issue -- visible publicly"),
    (r"gh\s+pr\s+merge", "Merges a pull request"),
    (r"gh\s+pr\s+close", "Closes a pull request"),
    (r"gh\s+release\s+create", "Creates a GitHub release -- public"),
    (r"open\s+", "Opens a file or URL with the default app"),
    (r"export\s+\w+=", "Sets environment variables for the session"),
    (r"source\s+", "Loads a script into the current shell"),
    (r"^\.\s+\S+", "Loads a script into the current shell (dot-source)"),
    (r"tee\s+", "Writes stdin to both stdout and a file"),
    (r">\s+\S+", "Redirects output -- overwrites target file"),
    (r">>\s+\S+", "Appends output to a file"),
]

# Safe: read-only, informational, local-only
_SAFE = [
    (r"^lsof\b", "Lists open files and network connections"),
    (r"^ls\b", "Lists directory contents"),
    (r"^ll\b", "Lists directory contents (detailed)"),
    (r"^la\b", "Lists all files including hidden"),
    (r"^cat\b", "Displays file contents"),
    (r"^head\b", "Shows the first lines of a file"),
    (r"^tail\b(?!.*-f)", "Shows the last lines of a file"),
    (r"^less\b", "Pages through file contents"),
    (r"^more\b", "Pages through file contents"),
    (r"^echo\b", "Prints text"),
    (r"^printf\b", "Prints formatted text"),
    (r"^pwd\b", "Shows the current directory"),
    (r"^whoami\b", "Shows the current user"),
    (r"^id\b", "Shows user/group IDs"),
    (r"^date\b", "Shows current date/time"),
    (r"^wc\b", "Counts lines/words/characters"),
    (r"^grep\b", "Searches text for patterns"),
    (r"^rg\b", "Searches text (ripgrep)"),
    (r"^ag\b", "Searches text (silver searcher)"),
    (r"^find\b", "Searches for files"),
    (r"^fd\b", "Searches for files (fd)"),
    (r"^which\b", "Shows location of a command"),
    (r"^where\b", "Shows location of a command"),
    (r"^type\b", "Shows how a command would be interpreted"),
    (r"^git\s+status\b", "Shows working tree status"),
    (r"^git\s+log\b", "Shows commit history"),
    (r"^git\s+diff\b", "Shows changes between commits/working tree"),
    (r"^git\s+show\b", "Shows details of a commit"),
    (r"^git\s+blame\b", "Shows who last modified each line"),
    (r"^git\s+branch\b(?!\s+-[dD])", "Lists or shows branches"),
    (r"^git\s+remote\s+-v", "Lists remote repositories"),
    (r"^git\s+tag\b(?!\s+-d)", "Lists tags"),
    (r"^git\s+rev-parse\b", "Resolves git references"),
    (r"^python3?\s+-c\b", "Runs a Python one-liner"),
    (r"^python3?\s+--version", "Shows Python version"),
    (r"^node\s+-e\b", "Runs a JavaScript one-liner"),
    (r"^node\s+--version", "Shows Node.js version"),
    (r"^jq\b", "Processes JSON data"),
    (r"^yq\b", "Processes YAML data"),
    (r"^tree\b", "Shows directory structure"),
    (r"^du\b", "Shows disk usage"),
    (r"^df\b", "Shows disk space"),
    (r"^uname\b", "Shows system information"),
    (r"^file\b", "Identifies file type"),
    (r"^stat\b", "Shows file metadata"),
    (r"^md5\b", "Computes file hash"),
    (r"^shasum\b", "Computes file hash"),
    (r"^realpath\b", "Resolves file path"),
    (r"^basename\b", "Strips directory from path"),
    (r"^dirname\b", "Strips filename from path"),
    (r"^env\b$", "Shows environment variables"),
    (r"^printenv\b", "Shows environment variables"),
    (r"^sort\b", "Sorts lines of text"),
    (r"^uniq\b", "Filters duplicate lines"),
    (r"^cut\b", "Extracts fields from lines"),
    (r"^tr\b", "Translates characters"),
    (r"^diff\b", "Compares files"),
    (r"^comm\b", "Compares sorted files"),
    (r"^test\b", "Tests file attributes or compares values"),
    (r"^\[\s+", "Tests file attributes or compares values"),
    (r"^true\b", "Does nothing successfully"),
    (r"^false\b", "Does nothing and fails"),
    (r"^gh\s+(issue|pr)\s+(list|view|status)", "Views GitHub issues/PRs (read-only)"),
    (r"^gh\s+api\s+", "Makes a GitHub API request"),
    (r"^kubectl\s+get\b", "Lists Kubernetes resources (read-only)"),
    (r"^kubectl\s+describe\b", "Shows details of Kubernetes resources"),
    (r"^kubectl\s+logs\b", "Shows container logs"),
    (r"^terraform\s+show\b", "Shows current Terraform state"),
    (r"^terraform\s+output\b", "Shows Terraform outputs"),
    (r"^terraform\s+state\s+list\b", "Lists resources in Terraform state"),
    (r"^aws\s+.*\s+(describe-|get-|list-)", "Reads AWS resource info (read-only)"),
    (r"^gcloud\s+.*\s+(describe|list)\b", "Reads Google Cloud resource info"),
    (r"^docker\s+ps\b", "Lists running containers"),
    (r"^docker\s+images\b", "Lists container images"),
    (r"^docker\s+logs\b", "Shows container logs"),
    (r"^make\s+-n\b", "Dry-run Makefile targets (no execution)"),
    (r"^cargo\s+check\b", "Checks Rust code without compiling"),
    (r"^cargo\s+clippy\b", "Runs Rust linter"),
    (r"^go\s+vet\b", "Runs Go static analysis"),
    (r"^npm\s+ls\b", "Lists installed npm packages"),
    (r"^pip\s+list\b", "Lists installed Python packages"),
    (r"^pip\s+show\b", "Shows Python package details"),
    (r"^pip\s+freeze\b", "Lists pinned Python packages"),
]

# Sensitive file patterns
_SENSITIVE_PATHS = [
    (r"\.env\b", "Environment file -- likely contains secrets or API keys"),
    (r"\.env\.\w+", "Environment file -- likely contains secrets"),
    (r"\bcredentials\b", "Credentials file -- may contain passwords or tokens"),
    (r"\.ssh/", "SSH directory -- contains private keys"),
    (r"\.aws/", "AWS config -- contains access keys"),
    (r"\.gcloud/", "Google Cloud config -- may contain tokens"),
    (r"\.kube/config", "Kubernetes config -- contains cluster credentials"),
    (r"\.git/config", "Git config -- may contain auth tokens"),
    (r"\.npmrc\b", "npm config -- may contain registry tokens"),
    (r"\.pypirc\b", "PyPI config -- contains upload tokens"),
    (r"\.netrc\b", "Network credentials file"),
    (r"id_rsa\b", "SSH private key"),
    (r"id_ed25519\b", "SSH private key"),
    (r"\.pem$", "Certificate or key file"),
    (r"\.key$", "Private key file"),
    (r"\.p12$", "PKCS#12 certificate bundle"),
    (r"\bsecret[s]?\b", "File with 'secret' in name -- review carefully"),
    (r"\bpassword[s]?\b", "File with 'password' in name -- review carefully"),
    (r"\btoken[s]?\b", "File with 'token' in name -- may contain auth tokens"),
    (r"docker-compose\.y[a]?ml", "Docker Compose config -- defines services and ports"),
    (r"Dockerfile", "Dockerfile -- defines container build"),
    (r"\.github/workflows/", "GitHub Actions workflow -- runs in CI"),
    (r"Makefile\b", "Makefile -- defines build recipes"),
    (r"/etc/", "System configuration directory"),
    (r"/usr/local/", "System-wide installation directory"),
]


# ---------------------------------------------------------------------------
# Bash analysis
# ---------------------------------------------------------------------------

def _split_pipeline(cmd: str) -> list[str]:
    """Split a command into pipe stages, respecting quotes."""
    stages = []
    current = []
    depth = 0
    in_sq = False
    in_dq = False
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c == "'" and not in_dq:
            in_sq = not in_sq
        elif c == '"' and not in_sq:
            in_dq = not in_dq
        elif c == '(' and not in_sq and not in_dq:
            depth += 1
        elif c == ')' and not in_sq and not in_dq:
            depth -= 1
        elif c == '|' and not in_sq and not in_dq and depth == 0:
            if i + 1 < len(cmd) and cmd[i + 1] == '|':
                current.append('||')
                i += 2
                continue
            stages.append(''.join(current).strip())
            current = []
            i += 1
            continue
        current.append(c)
        i += 1
    remainder = ''.join(current).strip()
    if remainder:
        stages.append(remainder)
    return stages


def _split_chain(cmd: str) -> list[tuple[str, str]]:
    """Split on && and || preserving the operator. Returns (operator, command) pairs."""
    parts = []
    current = []
    depth = 0
    in_sq = False
    in_dq = False
    i = 0
    op = ""
    while i < len(cmd):
        c = cmd[i]
        if c == "'" and not in_dq:
            in_sq = not in_sq
        elif c == '"' and not in_sq:
            in_dq = not in_dq
        elif c == '(' and not in_sq and not in_dq:
            depth += 1
        elif c == ')' and not in_sq and not in_dq:
            depth -= 1
        elif not in_sq and not in_dq and depth == 0:
            if c == '&' and i + 1 < len(cmd) and cmd[i + 1] == '&':
                text = ''.join(current).strip()
                if text:
                    parts.append((op, text))
                op = "&&"
                current = []
                i += 2
                continue
            elif c == '|' and i + 1 < len(cmd) and cmd[i + 1] == '|':
                text = ''.join(current).strip()
                if text:
                    parts.append((op, text))
                op = "||"
                current = []
                i += 2
                continue
            elif c == ';' and i + 1 < len(cmd) and cmd[i + 1] != ';':
                text = ''.join(current).strip()
                if text:
                    parts.append((op, text))
                op = ";"
                current = []
                i += 1
                continue
        current.append(c)
        i += 1
    remainder = ''.join(current).strip()
    if remainder:
        parts.append((op, remainder))
    return parts


def _detect_redirects(cmd: str) -> list[str]:
    """Find redirections in a command and explain them."""
    notes = []
    if re.search(r"2>&1", cmd):
        notes.append("stderr merged into stdout")
    if re.search(r"2>/dev/null", cmd):
        notes.append("errors silenced")
    if re.search(r">/dev/null", cmd):
        notes.append("output discarded")
    if re.search(r">>\s*\S+", cmd):
        target = re.search(r">>\s*(\S+)", cmd)
        if target:
            notes.append(f"appends to {_shorten_path(target.group(1))}")
    elif re.search(r">\s*\S+", cmd) and not re.search(r"2>|>&", cmd):
        target = re.search(r">\s*(\S+)", cmd)
        if target and target.group(1) != "/dev/null":
            notes.append(f"overwrites {_shorten_path(target.group(1))}")
    return notes


def _get_binary(cmd: str) -> str:
    """Extract the binary name from a command string."""
    cleaned = re.sub(r"^\s*(sudo\s+|env\s+\S+=\S+\s+)*", "", cmd)
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        parts = cleaned.split()
    if not parts:
        return ""
    return parts[0].split("/")[-1]


def _short_cmd(cmd: str, max_len: int = 40) -> str:
    """Return a short version of a command for use as a title."""
    s = cmd.strip()
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _cmd_label(cmd: str) -> str:
    """Short label for a command, e.g. 'git push', 'npm install', 'rm -rf'."""
    binary = _get_binary(cmd)
    stripped = cmd.strip()
    try:
        parts = shlex.split(stripped)
    except ValueError:
        parts = stripped.split()
    if binary in ("git", "npm", "npx", "yarn", "pnpm", "pip", "kubectl",
                   "docker", "terraform", "aws", "gcloud", "gh", "cargo",
                   "go", "brew"):
        if len(parts) >= 2:
            return f"{binary} {parts[1]}"
    if binary == "rm" and len(parts) >= 2 and parts[1].startswith("-"):
        return f"rm {parts[1]}"
    return binary


def _classify_single_cmd(cmd: str) -> tuple[str, str, str]:
    """Classify a single command (no pipes/chains). Returns (risk, title, explanation)."""
    stripped = cmd.strip()
    title = _short_cmd(stripped)

    for pattern, desc in _DANGER:
        if re.search(pattern, stripped, re.IGNORECASE):
            return ("danger", title, desc)

    for pattern, desc in _CAUTION:
        if re.search(pattern, stripped, re.IGNORECASE):
            return ("caution", title, desc)

    for pattern, desc in _SAFE:
        if re.search(pattern, stripped, re.IGNORECASE):
            return ("safe", title, desc)

    binary = _get_binary(stripped)
    if binary:
        return ("caution", title, f"Runs {binary} -- review what this does before allowing")
    return ("caution", title, "Could not parse command -- review before allowing")


def _compute_scope(cmd: str) -> tuple[str, str]:
    """Determine scope text and blast radius for a bash command."""
    if re.search(r"git\s+push|curl|wget|\bssh\s+\S|scp\s+|rsync\s+|npm\s+publish|gh\s+(pr|issue|release)\s+create|gh\s+pr\s+merge|terraform\s+apply|kubectl\s+apply|aws\s+|gcloud\s+", cmd):
        return ("Affects remote systems -- visible to others.", "remote")
    if re.search(r"docker|kubectl|terraform|brew\s+install|apt\s+install|pip\s+install|npm\s+install", cmd):
        return ("Modifies system or project dependencies.", "system")
    if re.search(r"\brm\b|\bmv\b|chmod|chown|sed\s+-i|>\s+\S+|tee\b|git\s+commit|git\s+add", cmd):
        return ("Modifies local files. Reversible with git if tracked.", "project")
    return ("Local only. No changes made.", "local")


def analyze_bash(command: str) -> Analysis:
    """Analyze a bash command with pipe/chain/redirect awareness."""
    cmd = command.strip()

    # Split chains FIRST so compound commands always get per-stage analysis
    chain_parts = _split_chain(cmd)

    # Multi-command chain (&&, ||, ;)
    if len(chain_parts) > 1:
        worst_risk = "safe"
        stages = []
        all_warnings = []
        risk_order = {"safe": 0, "caution": 1, "danger": 2}

        for op, part in chain_parts:
            risk, title, explanation = _classify_single_cmd(part)
            if risk_order.get(risk, 0) > risk_order.get(worst_risk, 0):
                worst_risk = risk
            label = f"{op + ' ' if op else ''}{_cmd_label(part)}: {explanation}"
            stages.append(label)
            all_warnings.extend(_check_sensitive_in_cmd(part))

        redirects = _detect_redirects(cmd)
        scope, blast = _compute_scope(cmd)
        icon_map = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}
        labels = [_cmd_label(part) for _, part in chain_parts]
        chain_title = ", then ".join(labels)
        if len(chain_title) > 40:
            chain_title = chain_title[:37] + "..."

        return Analysis(
            risk=worst_risk,
            icon=icon_map.get(worst_risk, "❓"),
            title=chain_title,
            explanation=f"Runs {len(chain_parts)} commands in order.",
            scope=scope,
            blast_radius=blast,
            warnings=all_warnings + [f"Redirect: {r}" for r in redirects],
            stages=stages,
        )

    # Single command or pipeline — check full-command danger patterns
    for pattern, desc in _DANGER:
        if re.search(pattern, cmd, re.IGNORECASE):
            scope, blast = _compute_scope(cmd)
            warnings = _check_sensitive_in_cmd(cmd)
            redirects = _detect_redirects(cmd)
            if redirects:
                warnings.extend([f"Redirect: {r}" for r in redirects])
            return Analysis(
                risk="danger",
                icon="⛔",
                title=_short_cmd(cmd),
                explanation=desc,
                scope=scope,
                blast_radius=blast,
                warnings=warnings,
            )

    # Pipeline (cmd | cmd | cmd)
    pipe_stages = _split_pipeline(cmd)
    if len(pipe_stages) > 1:
        worst_risk = "safe"
        stages = []
        all_warnings = []
        risk_order = {"safe": 0, "caution": 1, "danger": 2}

        for i, stage in enumerate(pipe_stages):
            risk, title, explanation = _classify_single_cmd(stage)
            if risk_order.get(risk, 0) > risk_order.get(worst_risk, 0):
                worst_risk = risk
            stages.append(f"{_get_binary(stage)}: {explanation}")
            all_warnings.extend(_check_sensitive_in_cmd(stage))

        redirects = _detect_redirects(cmd)
        scope, blast = _compute_scope(cmd)
        icon_map = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}
        pipe_title = " | ".join(_get_binary(s) for s in pipe_stages)
        if len(pipe_title) > 40:
            pipe_title = pipe_title[:37] + "..."

        return Analysis(
            risk=worst_risk,
            icon=icon_map.get(worst_risk, "❓"),
            title=pipe_title,
            explanation=f"Pipes output through {len(pipe_stages)} commands.",
            scope=scope,
            blast_radius=blast,
            warnings=all_warnings + [f"Redirect: {r}" for r in redirects],
            stages=stages,
        )

    # Single command
    risk, title, explanation = _classify_single_cmd(cmd)
    scope, blast = _compute_scope(cmd)
    warnings = _check_sensitive_in_cmd(cmd)
    redirects = _detect_redirects(cmd)
    if redirects:
        warnings.extend([f"Redirect: {r}" for r in redirects])

    # Bump risk if touching highly sensitive paths
    if warnings and risk == "safe":
        _HIGH = ("SSH", "private key", "secret", "credentials", "password")
        if any(kw.lower() in w.lower() for w in warnings for kw in _HIGH):
            risk = "danger"
        else:
            risk = "caution"

    icon_map = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}

    return Analysis(
        risk=risk,
        icon=icon_map.get(risk, "❓"),
        title=title,
        explanation=explanation,
        scope=scope,
        blast_radius=blast,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# File operation analysis
# ---------------------------------------------------------------------------

def _classify_edit_content(old_string: str, new_string: str, file_path: str) -> tuple[str, list[str]]:
    """Analyze what an edit is actually changing and return (description, notes)."""
    notes = []

    ext = os.path.splitext(file_path)[1].lower()
    basename = os.path.basename(file_path).lower()

    # Detect what kind of change
    if not old_string and new_string:
        action = "Inserting new content"
    elif old_string and not new_string:
        action = "Deleting content"
    else:
        action = "Replacing content"

    # Check for import/export changes
    import_pat = r"^\s*(import |from |require\(|export |module\.exports)"
    old_has_import = bool(re.search(import_pat, old_string, re.MULTILINE)) if old_string else False
    new_has_import = bool(re.search(import_pat, new_string, re.MULTILINE)) if new_string else False
    if old_has_import or new_has_import:
        notes.append("Changes imports/exports -- may affect other files")

    # Check for function/class signature changes
    sig_pat = r"^\s*(def |class |function |const \w+ = |async function |export (default )?function )"
    old_has_sig = bool(re.search(sig_pat, old_string, re.MULTILINE)) if old_string else False
    new_has_sig = bool(re.search(sig_pat, new_string, re.MULTILINE)) if new_string else False
    if old_has_sig and new_has_sig:
        notes.append("Modifies function/class signature -- callers may need updates")
    elif old_has_sig and not new_has_sig:
        notes.append("Removes a function/class definition")
    elif not old_has_sig and new_has_sig:
        notes.append("Adds a new function/class definition")

    # Check for env var / config value changes
    env_pat = r"[A-Z_]{3,}=|process\.env\.|os\.environ|getenv\(|\.env\b"
    if (old_string and re.search(env_pat, old_string)) or (new_string and re.search(env_pat, new_string)):
        notes.append("Touches environment variables or config values")

    # Config files get special attention
    config_names = {"package.json", "tsconfig.json", "pyproject.toml", "cargo.toml",
                    "go.mod", "go.sum", "requirements.txt", "setup.py", "setup.cfg",
                    ".eslintrc", ".prettierrc", "jest.config", "vite.config",
                    "webpack.config", "babel.config", "docker-compose.yml",
                    "dockerfile", "makefile", ".github", "ci.yml", "cd.yml"}
    if any(basename.startswith(n) or basename == n for n in config_names):
        notes.append("Config file -- changes may affect build, CI, or deployment")

    # Size info
    old_lines = old_string.count("\n") + 1 if old_string else 0
    new_lines = new_string.count("\n") + 1 if new_string else 0
    action += f" ({old_lines} -> {new_lines} lines)" if old_string and new_string else f" ({new_lines} lines)"

    return action, notes


def analyze_edit(file_path: str, old_string: str, new_string: str) -> Analysis:
    """Analyze a file edit operation."""
    path_warnings = _check_sensitive_paths(file_path)
    action, content_notes = _classify_edit_content(old_string, new_string, file_path)
    all_warnings = path_warnings + content_notes

    risk = "danger" if path_warnings else ("caution" if content_notes else "caution")
    icon = "⛔" if path_warnings else "✏️"

    if old_string and new_string and len(old_string.strip()) < 40 and len(new_string.strip()) < 40:
        explanation = f"'{old_string.strip()}' -> '{new_string.strip()}' in {_shorten_path(file_path)}"
    else:
        explanation = f"{action} in {_shorten_path(file_path)}."

    return Analysis(
        risk=risk,
        icon=icon,
        title=f"Edit -- {_shorten_path(file_path)}",
        explanation=explanation,
        scope="Local file. Reversible with git or undo.",
        blast_radius="project",
        warnings=all_warnings,
    )


def analyze_write(file_path: str, content: str) -> Analysis:
    """Analyze a file write (create/overwrite) operation."""
    path_warnings = _check_sensitive_paths(file_path)
    exists = os.path.exists(file_path)
    lines = content.count("\n") + 1

    if exists:
        action = "Overwriting existing file"
        risk = "caution"
    else:
        action = "Creating new file"
        risk = "safe"

    if path_warnings:
        risk = "danger"

    # Check if writing to CI/build config
    basename = os.path.basename(file_path).lower()
    ci_patterns = [".github/workflows/", "jenkinsfile", ".gitlab-ci", ".circleci",
                   "dockerfile", "docker-compose", "makefile"]
    if any(p in file_path.lower() for p in ci_patterns):
        path_warnings.append("CI/build config -- changes affect automated pipelines")

    icon_map = {"safe": "✅", "caution": "⚠️", "danger": "⛔"}
    return Analysis(
        risk=risk,
        icon=icon_map[risk],
        title=f"{'Overwrite' if exists else 'Create'} -- {_shorten_path(file_path)}",
        explanation=f"{action}: {_shorten_path(file_path)} ({lines} lines).",
        scope="Local file." + (" Overwrites existing content!" if exists else ""),
        blast_radius="project",
        warnings=path_warnings,
    )


def analyze_read(file_path: str) -> Analysis:
    """Analyze a file read operation."""
    warnings = _check_sensitive_paths(file_path)
    _HIGH_SENSITIVITY = ("SSH", "private key", "secret", "credentials", "password")
    is_high = any(kw.lower() in w.lower() for w in warnings for kw in _HIGH_SENSITIVITY)
    if is_high:
        risk = "danger"
        icon = "⛔"
    elif warnings:
        risk = "caution"
        icon = "⚠️"
    else:
        risk = "safe"
        icon = "📄"
    return Analysis(
        risk=risk,
        icon=icon,
        title=f"Read -- {_shorten_path(file_path)}",
        explanation=f"Reading {_shorten_path(file_path)}.",
        scope="Read-only. No changes made.",
        blast_radius="local",
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

def analyze_tool(tool_name: str, tool_input: dict) -> Optional[Analysis]:
    """Analyze any tool call and return a structured explanation."""
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
        desc = tool_input.get("description", tool_input.get("prompt", "unknown task")[:60])
        return Analysis(
            risk="safe",
            icon="🤖",
            title="Launching sub-agent",
            explanation=f"Spawning agent: {desc}.",
            scope="Runs in a sandboxed context with its own permissions.",
            blast_radius="local",
        )

    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        domain = re.sub(r"https?://([^/]+).*", r"\1", url) if url else "unknown"
        return Analysis(
            risk="caution",
            icon="🌐",
            title=f"Fetch -- {domain}",
            explanation=f"Downloading content from {domain}.",
            scope="Network request. Sends your IP to the target server.",
            blast_radius="remote",
        )

    elif tool_name in ("Grep", "Glob", "Search"):
        pattern = tool_input.get("pattern", tool_input.get("query", ""))
        return Analysis(
            risk="safe",
            icon="🔍",
            title=f"Search -- {tool_name}",
            explanation=f"Searching codebase for: {pattern[:50]}." if pattern else "Searching the codebase.",
            scope="Read-only. No changes made.",
            blast_radius="local",
        )

    elif tool_name == "Workflow":
        return Analysis(
            risk="caution",
            icon="🔄",
            title="Workflow",
            explanation="Running a multi-agent workflow -- multiple sub-agents will execute tasks.",
            scope="Spawns multiple agents. Each asks its own permissions.",
            blast_radius="project",
        )

    elif tool_name == "AskUserQuestion":
        return Analysis(
            risk="safe",
            icon="💬",
            title="Asking you a question",
            explanation="Claude needs your input before continuing.",
            scope="No action taken -- waiting for your response.",
            blast_radius="local",
        )

    elif tool_name == "NotebookEdit":
        return Analysis(
            risk="caution",
            icon="📓",
            title="Notebook edit",
            explanation=f"Modifying a Jupyter notebook cell.",
            scope="Local file. Reversible.",
            blast_radius="project",
        )

    else:
        return Analysis(
            risk="caution",
            icon="❓",
            title=f"Tool: {tool_name}",
            explanation=f"Claude wants to use the {tool_name} tool. Review parameters before approving.",
            scope="Unknown scope -- check tool documentation.",
            blast_radius="local",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_sensitive_paths(path: str) -> list[str]:
    warnings = []
    for pattern, desc in _SENSITIVE_PATHS:
        if re.search(pattern, path, re.IGNORECASE):
            warnings.append(desc)
    return warnings


def _check_sensitive_in_cmd(cmd: str) -> list[str]:
    warnings = []
    for pattern, desc in _SENSITIVE_PATHS:
        if re.search(pattern, cmd, re.IGNORECASE):
            warnings.append(f"Touches sensitive path: {desc}")
    return warnings


def _shorten_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    parts = path.split("/")
    if len(parts) > 4:
        return parts[0] + "/" + parts[1] + "/.../" + "/".join(parts[-2:])
    return path
