import json

import httpx
import pytest
import respx

from ai_code_review.llm.enterprise import EnterpriseProvider
from ai_code_review.llm.base import Severity
from ai_code_review.exceptions import ProviderError


@pytest.fixture
def provider():
    return EnterpriseProvider(
        base_url="https://llm.internal.company.com",
        api_path="/v1/chat/completions",
        model="internal-codellama-70b",
        auth_type="bearer",
        auth_token="test-token",
    )


class TestEnterpriseHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            side_effect=httpx.ConnectError("refused")
        )
        ok, msg = provider.health_check()
        assert ok is False
        assert msg


class TestEnterpriseReviewCode:
    @respx.mock
    def test_parses_response(self, provider):
        issues_json = json.dumps([
            {"severity": "warning", "file": "hal.c", "line": 5, "message": "hardcoded password"}
        ])
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": issues_json}}]
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING

    @respx.mock
    def test_sends_bearer_auth(self, provider):
        route = respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "[]"}}]
            })
        )
        provider.review_code("diff", "prompt")
        assert route.calls[0].request.headers["Authorization"] == "Bearer test-token"


class TestEnterpriseImproveCommitMsg:
    @respx.mock
    def test_returns_improved_message(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "[BSP-1] improved message"}}]
            })
        )
        result = provider.improve_commit_msg("[BSP-1] bad msg", "diff")
        assert result == "[BSP-1] improved message"


class TestEnterpriseChatErrorWrapping:
    """_chat() errors should be wrapped in ProviderError."""

    @respx.mock
    def test_review_code_wraps_connection_error(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(ProviderError, match="Enterprise API request failed"):
            provider.review_code("diff", "prompt")

    @respx.mock
    def test_improve_commit_msg_wraps_timeout_error(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with pytest.raises(ProviderError, match="Enterprise API request failed"):
            provider.improve_commit_msg("[BSP-1] msg", "diff")

    @respx.mock
    def test_wraps_http_status_error(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(ProviderError, match="Enterprise API request failed"):
            provider.review_code("diff", "prompt")

    @respx.mock
    def test_wraps_malformed_response(self, provider):
        """Missing expected keys in response JSON raises ProviderError."""
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"unexpected": "structure"})
        )
        with pytest.raises(ProviderError, match="Enterprise API request failed"):
            provider.review_code("diff", "prompt")

    @respx.mock
    def test_original_exception_chained(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(ProviderError) as exc_info:
            provider.review_code("diff", "prompt")
        assert exc_info.value.__cause__ is not None


class TestEnterpriseTimeout:
    def test_default_timeout(self):
        p = EnterpriseProvider(
            base_url="https://llm.example.com", api_path="/v1/chat/completions",
            model="model", auth_type="bearer", auth_token="tok",
        )
        assert p._client.timeout.connect == 120.0

    def test_custom_timeout(self):
        p = EnterpriseProvider(
            base_url="https://llm.example.com", api_path="/v1/chat/completions",
            model="model", auth_type="bearer", auth_token="tok", timeout=60,
        )
        assert p._client.timeout.connect == 60.0
