import json
from unittest.mock import MagicMock, patch

import openai
import pytest

from ai_code_review.llm.openai import OpenAIProvider
from ai_code_review.llm.base import Severity
from ai_code_review.exceptions import ProviderError


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
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_unhealthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.side_effect = Exception("connection refused")
        provider._client = mock_cls.return_value
        ok, msg = provider.health_check()
        assert ok is False
        assert "connection refused" in msg.lower()


class TestOpenAIGenerateCommitMsg:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_generates_commit_message(self, mock_cls, provider, mock_openai_response):
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(
            "fix null pointer in camera init"
        )
        provider._client = mock_cls.return_value

        result = provider.generate_commit_msg("+ if (ptr == NULL) return;")
        assert result == "fix null pointer in camera init"

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_strips_whitespace(self, mock_cls, provider, mock_openai_response):
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(
            "  fix null pointer in camera init  \n"
        )
        provider._client = mock_cls.return_value

        result = provider.generate_commit_msg("+ if (ptr == NULL) return;")
        assert result == "fix null pointer in camera init"


class TestOpenAIChatErrorWrapping:
    """_chat() errors should be wrapped in ProviderError."""

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_review_code_wraps_connection_error(self, mock_cls, provider):
        mock_cls.return_value.chat.completions.create.side_effect = (
            openai.APIConnectionError(request=MagicMock())
        )
        provider._client = mock_cls.return_value
        with pytest.raises(ProviderError, match="OpenAI API request failed"):
            provider.review_code("diff", "prompt")

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_improve_commit_msg_wraps_timeout_error(self, mock_cls, provider):
        mock_cls.return_value.chat.completions.create.side_effect = (
            openai.APITimeoutError(request=MagicMock())
        )
        provider._client = mock_cls.return_value
        with pytest.raises(ProviderError, match="OpenAI API request failed"):
            provider.improve_commit_msg("[BSP-1] msg", "diff")

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_wraps_api_status_error(self, mock_cls, provider):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_cls.return_value.chat.completions.create.side_effect = (
            openai.APIStatusError(
                message="Internal server error",
                response=mock_response,
                body=None,
            )
        )
        provider._client = mock_cls.return_value
        with pytest.raises(ProviderError, match="OpenAI API request failed"):
            provider.review_code("diff", "prompt")

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_original_exception_chained(self, mock_cls, provider):
        mock_cls.return_value.chat.completions.create.side_effect = (
            openai.APIConnectionError(request=MagicMock())
        )
        provider._client = mock_cls.return_value
        with pytest.raises(ProviderError) as exc_info:
            provider.review_code("diff", "prompt")
        assert exc_info.value.__cause__ is not None
