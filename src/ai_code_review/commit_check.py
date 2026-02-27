from __future__ import annotations

import re
from dataclasses import dataclass

_COMMIT_MSG_PATTERN = re.compile(
    r"^\[[A-Z]+-\d+\] .+"
)

_FORMAT_HINT = "Expected format: [PROJECT-NUMBER] description  (e.g. [BSP-456] fix camera HAL crash)"


@dataclass(frozen=True)
class CommitCheckResult:
    valid: bool
    error: str | None = None


def check_commit_message(message: str) -> CommitCheckResult:
    message = message.strip()
    if not message:
        return CommitCheckResult(valid=False, error=f"Commit message is empty. {_FORMAT_HINT}")
    if not _COMMIT_MSG_PATTERN.match(message):
        return CommitCheckResult(valid=False, error=f"Invalid commit message format. {_FORMAT_HINT}")
    return CommitCheckResult(valid=True)
