"""Workflow pattern recognition — detects what Claude is doing across multiple steps.

Recognizes common multi-step patterns and tells the user where they are
in the workflow, so a permission prompt has context beyond the single tool call.
"""

from dataclasses import dataclass
from typing import Optional

# Each pattern is a sequence of tool categories that form a recognizable workflow.
# The detector matches the tail of session history against these patterns.


@dataclass
class WorkflowMatch:
    name: str           # short slug
    label: str          # human-readable name
    description: str    # what this workflow means
    stage: int          # which step we're at (0-indexed)
    total: int          # total steps in matched pattern
    confidence: float   # 0.0 - 1.0


# Categories map tool events to abstract categories for pattern matching
def categorize(tool_name: str, summary: str = "", file_path: str = None) -> str:
    """Map a tool event into an abstract category for pattern matching."""
    t = tool_name.lower()
    s = summary.lower()

    if t == "read":
        return "read"
    if t in ("grep", "glob", "search"):
        return "search"
    if t == "edit":
        return "edit"
    if t == "write":
        return "write"
    if t == "agent":
        return "agent"
    if t == "bash":
        if any(k in s for k in ["git status", "git log", "git diff", "git show", "git blame"]):
            return "git-inspect"
        if any(k in s for k in ["git add", "git commit"]):
            return "git-stage"
        if "git push" in s:
            return "git-push"
        if any(k in s for k in ["test", "pytest", "jest", "cargo test", "go test", "npm test"]):
            return "test"
        if any(k in s for k in ["lists directory", "read-only", "shows"]):
            return "explore"
        if any(k in s for k in ["install", "build", "compile"]):
            return "build"
        return "bash"
    return "other"


# Pattern definitions: (name, label, description, category_sequence)
# The sequence is matched against the end of the history.
# '*' matches any single category.
_PATTERNS = [
    (
        "explore",
        "Exploring",
        "Claude is reading and searching to understand the codebase",
        ["read|search|explore|git-inspect"] * 3,
    ),
    (
        "modify",
        "Read -> Edit",
        "Claude read a file and now wants to modify it",
        ["read", "edit"],
    ),
    (
        "multi-edit",
        "Multi-file refactor",
        "Claude is editing multiple files in sequence",
        ["edit", "edit"],
    ),
    (
        "verify-edit",
        "Edit -> Verify",
        "Claude edited a file and is reading it back to verify",
        ["edit", "read"],
    ),
    (
        "test-fix",
        "Test -> Fix -> Test",
        "Claude ran tests, saw failures, edited code, and is testing again",
        ["test", "edit|write", "test"],
    ),
    (
        "fix-cycle",
        "Fix cycle",
        "Claude is editing code and running tests to verify the fix",
        ["edit", "test"],
    ),
    (
        "deploy",
        "Stage -> Commit -> Push",
        "Claude is deploying changes to the remote repository",
        ["git-stage", "git-stage|git-push", "git-push"],
    ),
    (
        "commit-flow",
        "Stage -> Commit",
        "Claude is staging and committing changes",
        ["git-stage", "git-stage"],
    ),
    (
        "investigate",
        "Investigating",
        "Claude is digging into git history and code to understand something",
        ["git-inspect", "read|search"],
    ),
    (
        "create",
        "Creating files",
        "Claude is writing new files",
        ["write", "write"],
    ),
    (
        "search-modify",
        "Search -> Modify",
        "Claude searched for something and now wants to change it",
        ["search", "read|edit"],
    ),
    (
        "build-test",
        "Build -> Test",
        "Claude built the project and is now running tests",
        ["build", "test"],
    ),
]


def _category_matches(actual: str, pattern_slot: str) -> bool:
    """Check if an actual category matches a pattern slot (supports | for alternatives)."""
    return actual in pattern_slot.split("|")


def detect_workflow(history: list[dict], current_tool: str, current_summary: str = "",
                    current_file: str = None) -> Optional[WorkflowMatch]:
    """Detect which workflow pattern the current operation is part of.

    Args:
        history: list of past tool events (dicts with tool_name, summary, file_path)
        current_tool: the tool being called now
        current_summary: summary of the current operation
        current_file: file path if applicable

    Returns:
        WorkflowMatch if a pattern is detected, None otherwise
    """
    current_cat = categorize(current_tool, current_summary, current_file)

    # Build category sequence from recent history + current
    recent = history[-5:] if len(history) > 5 else history
    cats = []
    for event in recent:
        cats.append(categorize(
            event.get("tool_name", ""),
            event.get("summary", ""),
            event.get("file_path"),
        ))
    cats.append(current_cat)

    best_match = None
    best_confidence = 0.0

    for name, label, description, pattern in _PATTERNS:
        plen = len(pattern)
        if plen > len(cats):
            continue

        # Try matching the pattern against the tail of the category sequence
        tail = cats[-plen:]
        matched = all(_category_matches(tail[i], pattern[i]) for i in range(plen))

        if matched:
            stage = plen - 1  # current operation is the last matched step
            confidence = min(1.0, plen / 3.0)  # longer patterns = higher confidence

            # Boost confidence if files match across steps
            if current_file and any(e.get("file_path") == current_file for e in recent):
                confidence = min(1.0, confidence + 0.2)

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = WorkflowMatch(
                    name=name,
                    label=label,
                    description=description,
                    stage=stage,
                    total=plen,
                    confidence=confidence,
                )

    return best_match


def detect_file_heat(history: list[dict], file_path: str) -> int:
    """Count how many times a file has been touched in this session."""
    if not file_path:
        return 0
    return sum(1 for e in history if e.get("file_path") == file_path)


def detect_repeated_denials(history: list[dict], tool_name: str) -> int:
    """Count recent denials for a tool type (if tracked)."""
    return sum(1 for e in history
               if e.get("tool_name") == tool_name and e.get("denied", False))
