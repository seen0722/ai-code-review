from __future__ import annotations

import httpx

from .base import LLMProvider, ReviewResult
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt

_DEFAULT_TIMEOUT = 120.0


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        transport = httpx.HTTPTransport(retries=3)
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def health_check(self) -> tuple[bool, str]:
        try:
            resp = self._client.get(f"{self._base_url}/api/tags")
            if resp.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, f"Connection refused: {self._base_url}"
        except httpx.TimeoutException:
            return False, f"Timeout connecting to {self._base_url}"
        except httpx.HTTPError as e:
            return False, str(e)

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = get_commit_improve_prompt(message, diff)
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
