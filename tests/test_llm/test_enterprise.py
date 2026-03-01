import json

import httpx
import pytest
import respx

from ai_code_review.llm.enterprise import EnterpriseProvider
from ai_code_review.llm.base import Severity


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
