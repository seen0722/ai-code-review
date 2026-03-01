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
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        ok, msg = provider.health_check()
        assert ok is False
        assert msg  # has a reason

    @respx.mock
    def test_unhealthy_http_error(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(500)
        )
        ok, msg = provider.health_check()
        assert ok is False
        assert "500" in msg


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


class TestParseReviewEdgeCases:
    @respx.mock
    def test_markdown_fence_json(self, provider):
        """LLM wraps response in ```json ... ``` fences."""
        content = '```json\n[{"severity":"warning","file":"a.c","line":1,"message":"test"}]\n```'
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING

    @respx.mock
    def test_markdown_fence_no_lang(self, provider):
        """LLM wraps response in ``` ... ``` without language tag."""
        content = '```\n[{"severity":"info","file":"b.c","line":5,"message":"note"}]\n```'
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.INFO

    @respx.mock
    def test_malformed_json(self, provider):
        """LLM returns invalid JSON — should return empty result, not crash."""
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "{not valid json}"}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0

    @respx.mock
    def test_empty_response(self, provider):
        """LLM returns empty string."""
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": ""}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0

    @respx.mock
    def test_missing_fields_skipped(self, provider):
        """Items missing required fields are skipped."""
        content = json.dumps([
            {"severity": "warning", "file": "a.c", "line": 1, "message": "ok"},
            {"severity": "warning"},  # missing file, line, message
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1  # only the valid one

    @respx.mock
    def test_invalid_severity_skipped(self, provider):
        """Items with invalid severity value are skipped."""
        content = json.dumps([
            {"severity": "fatal", "file": "a.c", "line": 1, "message": "bad severity"},
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0


class TestOllamaTimeout:
    def test_default_timeout(self):
        p = OllamaProvider(base_url="http://localhost:11434", model="codellama")
        assert p._client.timeout.connect == 120.0

    def test_custom_timeout(self):
        p = OllamaProvider(base_url="http://localhost:11434", model="codellama", timeout=30)
        assert p._client.timeout.connect == 30.0
