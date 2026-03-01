from unittest.mock import MagicMock

import pytest

from ai_code_review.reviewer import Reviewer
from ai_code_review.llm.base import ReviewResult, ReviewIssue, Severity


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.review_code.return_value = ReviewResult(issues=[
        ReviewIssue(severity=Severity.WARNING, file="a.c", line=1, message="minor"),
    ])
    provider.improve_commit_msg.return_value = "[BSP-1] improved message"
    provider.health_check.return_value = (True, "Connected")
    return provider


@pytest.fixture
def reviewer(mock_provider):
    return Reviewer(provider=mock_provider)


class TestReviewDiff:
    def test_calls_provider_with_diff(self, reviewer, mock_provider):
        reviewer.review_diff("some diff content")
        mock_provider.review_code.assert_called_once()
        args = mock_provider.review_code.call_args
        assert "some diff content" in args[0]

    def test_returns_review_result(self, reviewer):
        result = reviewer.review_diff("diff")
        assert isinstance(result, ReviewResult)
        assert len(result.issues) == 1


    def test_passes_custom_rules_to_prompt(self, reviewer, mock_provider):
        reviewer.review_diff("diff", custom_rules="check integer overflow")
        prompt_arg = mock_provider.review_code.call_args[0][1]
        assert "integer overflow" in prompt_arg

    def test_no_custom_rules_uses_default_prompt(self, reviewer, mock_provider):
        reviewer.review_diff("diff")
        prompt_arg = mock_provider.review_code.call_args[0][1]
        assert "Additional rules" not in prompt_arg


class TestImproveCommitMessage:
    def test_calls_provider(self, reviewer, mock_provider):
        reviewer.improve_commit_message("[BSP-1] fix bug", "diff")
        mock_provider.improve_commit_msg.assert_called_once_with("[BSP-1] fix bug", "diff")

    def test_returns_improved_message(self, reviewer):
        result = reviewer.improve_commit_message("[BSP-1] fix bug", "diff")
        assert result == "[BSP-1] improved message"


class TestHealthCheck:
    def test_delegates_to_provider(self, reviewer, mock_provider):
        mock_provider.health_check.return_value = (True, "Connected")
        ok, msg = reviewer.check_provider_health()
        assert ok is True
        mock_provider.health_check.assert_called_once()
