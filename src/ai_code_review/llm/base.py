from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class Severity(Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def blocks(self) -> bool:
        return self in (Severity.CRITICAL, Severity.ERROR)


@dataclass(frozen=True)
class ReviewIssue:
    severity: Severity
    file: str
    line: int
    message: str


@dataclass
class ReviewResult:
    issues: list[ReviewIssue] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return any(issue.severity.blocks for issue in self.issues)

    @property
    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts


class LLMProvider(ABC):
    @abstractmethod
    def review_code(self, diff: str, prompt: str) -> ReviewResult: ...

    @abstractmethod
    def improve_commit_msg(self, message: str, diff: str) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...

    def _parse_review(self, content: str) -> ReviewResult:
        try:
            text = content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            items = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM review response: %s", content[:200])
            return ReviewResult()

        issues = []
        for item in items:
            try:
                issues.append(ReviewIssue(
                    severity=Severity(item["severity"]),
                    file=item["file"],
                    line=int(item["line"]),
                    message=item["message"],
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed issue: %s (%s)", item, e)
        return ReviewResult(issues=issues)
