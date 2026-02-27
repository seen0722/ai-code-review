from __future__ import annotations

_REVIEW_PROMPT = """\
You are a senior Android BSP engineer. Review the following git diff and report only serious issues.

Focus on:
- Memory leaks (malloc without free, unreleased resources)
- Null pointer dereference
- Race conditions, missing lock/mutex protection
- Hardcoded secrets (keys, passwords, tokens)
- Obvious logic errors
- Buffer overflow

Do not report:
- Code style or naming suggestions
- Performance optimization suggestions
- Refactoring suggestions

Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""

_COMMIT_IMPROVE_PROMPT = """\
You are a technical writing assistant. Given the original commit message and the git diff:
1. Fix English grammar errors
2. Make the description accurately reflect the code changes
3. Keep it under 72 characters total
4. Preserve the [PROJECT-NUMBER] prefix exactly as-is

Respond with only the improved commit message. No explanation, no quotes.

Original: {message}

Diff:
{diff}"""


def get_review_prompt() -> str:
    return _REVIEW_PROMPT


def get_commit_improve_prompt(message: str, diff: str) -> str:
    return _COMMIT_IMPROVE_PROMPT.format(message=message, diff=diff)
