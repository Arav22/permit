"""Cost estimation for Claude Code tool calls."""

import os
import re
from dataclasses import dataclass, field

_PRICING = {
    "opus":   {"input": 15.00, "output": 75.00, "cached": 1.88},
    "sonnet": {"input":  3.00, "output": 15.00, "cached": 0.38},
    "haiku":  {"input":  0.80, "output":  4.00, "cached": 0.10},
}

_CHARS_PER_TOKEN = 4

_BASH_OUTPUT_ESTIMATES = {
    "python3 -m pytest": 1500,
    "git log": 1000, "git diff": 800, "git show": 600,
    "git status": 100, "git branch": 50,
    "git add": 50, "git commit": 100, "git push": 100,
    "pytest": 1500, "npm test": 1500, "cargo test": 1500,
    "npm run": 400, "make": 400,
    "find": 300, "tree": 300,
    "grep": 250, "rg": 250, "ag": 250,
    "kubectl get": 300, "docker ps": 150,
    "cat": 150, "head": 100, "tail": 100, "less": 150, "du": 100,
    "ls": 50,
    "echo": 30, "pwd": 20, "whoami": 20, "date": 20,
}


@dataclass
class CostEstimate:
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tips: list[str] = field(default_factory=list)


def _detect_model() -> str:
    for var in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "AWS_BEDROCK_MODEL", "BEDROCK_MODEL_ID"):
        val = os.environ.get(var, "").lower()
        if not val:
            continue
        if "haiku" in val:
            return "haiku"
        if "sonnet" in val:
            return "sonnet"
        # opus and fable both map to the premium tier
        if "opus" in val or "fable" in val:
            return "opus"
    return "opus"


def _chars_to_tokens(n: int) -> int:
    return max(1, n // _CHARS_PER_TOKEN)


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 4000


def _file_lines(path: str) -> int:
    try:
        with open(path, "r") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _bash_output_tokens(command: str) -> int:
    cmd = command.strip()
    for prefix, tokens in sorted(_BASH_OUTPUT_ESTIMATES.items(), key=lambda x: -len(x[0])):
        if cmd.startswith(prefix):
            return tokens
    return 100


def _estimate_read(tool_input: dict) -> tuple[int, int]:
    path = tool_input.get("file_path", "")
    input_t = _chars_to_tokens(len(path) + 50)
    output_t = _chars_to_tokens(_file_size(path))
    return input_t, output_t


def _estimate_write(tool_input: dict) -> tuple[int, int]:
    content = tool_input.get("content", "")
    input_t = _chars_to_tokens(len(content) + 100)
    return input_t, 50


def _estimate_edit(tool_input: dict) -> tuple[int, int]:
    old = tool_input.get("old_string", "")
    new = tool_input.get("new_string", "")
    path = tool_input.get("file_path", "")
    input_t = _chars_to_tokens(len(old) + len(new) + len(path) + 100)
    return input_t, 50


def _estimate_bash(tool_input: dict) -> tuple[int, int]:
    cmd = tool_input.get("command", "")
    input_t = _chars_to_tokens(len(cmd) + 50)
    output_t = _bash_output_tokens(cmd)
    return input_t, output_t


def _estimate_agent(tool_input: dict) -> tuple[int, int]:
    prompt = tool_input.get("prompt", tool_input.get("description", ""))
    input_t = 2000 + _chars_to_tokens(len(prompt))
    return input_t, 5000


def _estimate_webfetch(tool_input: dict) -> tuple[int, int]:
    url = tool_input.get("url", "")
    input_t = _chars_to_tokens(len(url) + 50)
    return input_t, 2000


def _estimate_generic(tool_input: dict) -> tuple[int, int]:
    input_t = _chars_to_tokens(len(str(tool_input)) + 50)
    return input_t, 200


_TOOL_ESTIMATORS = {
    "Read": _estimate_read,
    "Write": _estimate_write,
    "Edit": _estimate_edit,
    "Bash": _estimate_bash,
    "Agent": _estimate_agent,
    "WebFetch": _estimate_webfetch,
}


def _calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    prices = _PRICING.get(model, _PRICING["opus"])
    input_cost = (input_tokens / 1_000_000) * prices["input"]
    output_cost = (output_tokens / 1_000_000) * prices["output"]
    return input_cost + output_cost


def generate_tips(tool_name: str, tool_input: dict, cost_usd: float, model: str) -> list[str]:
    tips = []

    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        has_limit = "limit" in tool_input or "offset" in tool_input
        lines = _file_lines(path)
        if lines > 500 and not has_limit:
            tips.append(f"This file is ~{lines} lines -- use offset/limit to read specific sections")

    if tool_name == "Agent":
        tips.append("Agent spawns are expensive -- consider doing this directly")

    if tool_name == "Write":
        content = tool_input.get("content", "")
        if content.count("\n") > 200:
            tips.append("Large write -- could you Edit specific sections instead?")

    if model == "opus" and cost_usd >= 0.02:
        tips.append("Switch to Sonnet for routine tasks (/model sonnet) -- ~5x cheaper")

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if re.search(r"\bpytest\b|\bnpm test\b|\bcargo test\b|\bmake test\b", cmd):
            if not re.search(r"\b-k\b|\btest_\w+\.py\b|::\w+", cmd):
                tips.append("Full test run -- consider running only relevant test files")

    return tips


def estimate_cost(tool_name: str, tool_input: dict, model: str = "") -> CostEstimate:
    if not model:
        model = _detect_model()
    model = model.lower()
    if model not in _PRICING:
        model = "opus"

    estimator = _TOOL_ESTIMATORS.get(tool_name, _estimate_generic)
    input_tokens, output_tokens = estimator(tool_input)

    cost_usd = _calculate_cost(input_tokens, output_tokens, model)
    tips = generate_tips(tool_name, tool_input, cost_usd, model)

    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tips=tips,
    )


def format_cost(cost_usd: float) -> str:
    if cost_usd < 0.001:
        return "~$0.001"
    if cost_usd < 0.01:
        return f"~${cost_usd:.3f}"
    if cost_usd < 1.0:
        return f"~${cost_usd:.2f}"
    return f"~${cost_usd:.2f}"


def format_tokens(tokens: int) -> str:
    if tokens >= 1000:
        return f"{tokens // 1000}K"
    return str(tokens)


def check_budget(session_cost: float, budget: float) -> str:
    """Returns '' if fine, 'caution' if approaching, 'danger' if exceeded."""
    if budget <= 0:
        return ""
    if session_cost >= budget:
        return "danger"
    if session_cost >= budget * 0.8:
        return "caution"
    return ""


def format_budget_bar(session_cost: float, budget: float) -> str:
    """Returns a budget bar string like: ~$3.20 / $5.00  [========--] 80%"""
    pct = min(1.0, session_cost / budget) if budget > 0 else 0
    filled = int(pct * 10)
    bar = "=" * filled + "-" * (10 - filled)
    pct_str = f"{int(pct * 100)}%"
    return f"{format_cost(session_cost)} / ${budget:.2f}  [{bar}] {pct_str}"
