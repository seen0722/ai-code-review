from __future__ import annotations

import httpx

from .base import LLMProvider, ReviewResult
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt


class EnterpriseProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_path: str,
        model: str,
        auth_type: str = "bearer",
        auth_token: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_path = api_path
        self._model = model
        self._headers = self._build_auth_headers(auth_type, auth_token)
        self._client = httpx.Client(timeout=120.0, headers=self._headers)

    @staticmethod
    def _build_auth_headers(auth_type: str, token: str) -> dict[str, str]:
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {token}"}
        elif auth_type == "api-key":
            return {"X-API-Key": token}
        else:
            return {"Authorization": token}

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self._base_url}/v1/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = get_commit_improve_prompt(message, diff)
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        resp = self._client.post(
            f"{self._base_url}{self._api_path}",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

