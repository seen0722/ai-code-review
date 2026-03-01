from __future__ import annotations

from openai import OpenAI

from .base import LLMProvider, ReviewResult
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def health_check(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = get_commit_improve_prompt(message, diff)
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
