import json
from unittest.mock import MagicMock, patch

import pytest

from ai_code_review.llm.openai import OpenAIProvider
from ai_code_review.llm.base import Severity


@pytest.fixture
def provider():
    return OpenAIProvider(api_key="sk-test", model="gpt-4o")


@pytest.fixture
def mock_openai_response():
    """Helper to create a mock OpenAI ChatCompletion response."""
    def _make(content: str):
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response
    return _make


class TestOpenAIReviewCode:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_parses_review_response(self, mock_cls, provider, mock_openai_response):
        issues_json = json.dumps([
            {"severity": "error", "file": "driver.c", "line": 10, "message": "null deref"}
        ])
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(issues_json)
        provider._client = mock_cls.return_value

        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.ERROR


class TestOpenAIImproveCommitMsg:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_returns_improved_message(self, mock_cls, provider, mock_openai_response):
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(
            "[BSP-456] fix camera HAL crash during boot sequence"
        )
        provider._client = mock_cls.return_value

        result = provider.improve_commit_msg("[BSP-456] fix crash when boot", "diff")
        assert result == "[BSP-456] fix camera HAL crash during boot sequence"


class TestOpenAIHealthCheck:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_healthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.return_value = []
        provider._client = mock_cls.return_value
        assert provider.health_check() is True

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_unhealthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.side_effect = Exception("connection refused")
        provider._client = mock_cls.return_value
        assert provider.health_check() is False
