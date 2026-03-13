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


class TestGenerateCommitMessage:
    def test_delegates_to_provider(self):
        mock_provider = MagicMock()
        mock_provider.generate_commit_msg.return_value = "fix buffer overflow"
        reviewer = Reviewer(provider=mock_provider)
        result = reviewer.generate_commit_message("some diff")
        assert result == "fix buffer overflow"
        mock_provider.generate_commit_msg.assert_called_once_with("some diff")


class TestPolishCommitMessage:
    def test_delegates_to_provider(self):
        provider = MagicMock()
        provider.polish_commit_msg.return_value = "polished"
        reviewer = Reviewer(provider=provider)
        result = reviewer.polish_commit_message("fix", "desc", "diff")
        assert result == "polished"
        provider.polish_commit_msg.assert_called_once()

    def test_passes_all_arguments(self):
        provider = MagicMock()
        provider.polish_commit_msg.return_value = "SUMMARY: polished\nDESCRIPTION: detailed"
        reviewer = Reviewer(provider=provider)
        reviewer.polish_commit_message("fix crash", "camera null ptr", "some diff")
        provider.polish_commit_msg.assert_called_once_with("fix crash", "camera null ptr", "some diff")


class TestHealthCheck:
    def test_delegates_to_provider(self, reviewer, mock_provider):
        mock_provider.health_check.return_value = (True, "Connected")
        ok, msg = reviewer.check_provider_health()
        assert ok is True
        mock_provider.health_check.assert_called_once()


class TestReviewDiffWithContext:
    def test_passes_file_contents_to_prompt(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)
        file_contents = {"main.c": "int main() {}"}
        reviewer.review_diff("diff content", file_contents=file_contents)
        prompt = provider.review_code.call_args[0][1]
        assert "main.c" in prompt
        assert "follow these steps" in prompt

    def test_no_file_contents_uses_basic_prompt(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)
        reviewer.review_diff("diff content")
        prompt = provider.review_code.call_args[0][1]
        assert "follow these steps" not in prompt

    def test_empty_file_contents_uses_basic_prompt(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)
        reviewer.review_diff("diff content", file_contents={})
        prompt = provider.review_code.call_args[0][1]
        assert "follow these steps" not in prompt

    def test_file_contents_with_custom_rules(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)
        file_contents = {"driver.c": "void init() {}"}
        reviewer.review_diff("diff", custom_rules="check buffer overflow", file_contents=file_contents)
        prompt = provider.review_code.call_args[0][1]
        assert "driver.c" in prompt
        assert "buffer overflow" in prompt
        assert "follow these steps" in prompt
