from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


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
