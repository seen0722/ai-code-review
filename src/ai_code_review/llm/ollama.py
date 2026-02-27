from __future__ import annotations

import json
import logging

import httpx

from .base import LLMProvider, ReviewIssue, ReviewResult, Severity

logger = logging.getLogger(__name__)

_REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=120.0)

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self._base_url}/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{_REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = (
            "You are a technical writing assistant. "
            "Given the original commit message and the git diff, "
            "fix English grammar and make the description more precise. "
            "Keep it under 72 characters. "
            "Preserve the [PROJECT-NUMBER] prefix. "
            "Respond with only the improved commit message, nothing else.\n\n"
            f"Original: {message}\n\nDiff:\n{diff}"
        )
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        resp = self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

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
