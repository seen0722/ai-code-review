from __future__ import annotations

import re
from dataclasses import dataclass

_COMMIT_MSG_PATTERN = re.compile(
    r"^(\[UPDATE\])?\[(BSP|CP|AP)\]\[[A-Z]+\] .+"
)

_FORMAT_HINT = (
    "Commit message must match: [CATEGORY][COMPONENT] description\n"
    "  Categories: BSP, CP, AP\n"
    "  Component must be UPPERCASE\n"
    "  Optional [UPDATE] prefix for follow-up commits\n"
    "  Examples:\n"
    "    [BSP][CAMERA] fix null pointer crash\n"
    "    [UPDATE][AP][NAL] update installation manager"
)


@dataclass(frozen=True)
class CommitCheckResult:
    valid: bool
    error: str | None = None


def check_commit_message(message: str) -> CommitCheckResult:
    message = message.strip()
    if not message:
        return CommitCheckResult(valid=False, error="Empty commit message.")
    first_line = message.split("\n")[0].strip()
    if not _COMMIT_MSG_PATTERN.match(first_line):
        return CommitCheckResult(valid=False, error=_FORMAT_HINT)
    return CommitCheckResult(valid=True)
