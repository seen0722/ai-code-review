from __future__ import annotations

from .llm.base import LLMProvider, ReviewResult
from .prompts import get_review_prompt


class Reviewer:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def review_diff(self, diff: str) -> ReviewResult:
        prompt = get_review_prompt()
        return self._provider.review_code(diff, prompt)

    def improve_commit_message(self, message: str, diff: str) -> str:
        return self._provider.improve_commit_msg(message, diff)

    def check_provider_health(self) -> bool:
        return self._provider.health_check()
