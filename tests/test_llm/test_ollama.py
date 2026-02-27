import json

import httpx
import pytest
import respx

from ai_code_review.llm.ollama import OllamaProvider
from ai_code_review.llm.base import Severity


@pytest.fixture
def provider():
    return OllamaProvider(base_url="http://localhost:11434", model="codellama")


class TestOllamaHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        assert provider.health_check() is True

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        assert provider.health_check() is False


class TestOllamaReviewCode:
    @respx.mock
    def test_parses_review_response(self, provider):
        llm_response = json.dumps([
            {"severity": "critical", "file": "hal.c", "line": 42, "message": "memory leak"}
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": llm_response}
            })
        )
        result = provider.review_code("diff content", "review prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.CRITICAL
        assert result.issues[0].file == "hal.c"

    @respx.mock
    def test_returns_empty_on_no_issues(self, provider):
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "[]"}
            })
        )
        result = provider.review_code("diff content", "review prompt")
        assert len(result.issues) == 0
        assert result.is_blocked is False


class TestOllamaImproveCommitMsg:
    @respx.mock
    def test_returns_improved_message(self, provider):
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "[BSP-456] fix camera HAL crash during boot sequence"}
            })
        )
        result = provider.improve_commit_msg("[BSP-456] fix camera HAL crash when boot", "diff")
        assert result == "[BSP-456] fix camera HAL crash during boot sequence"
