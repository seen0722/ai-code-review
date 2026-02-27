from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main
from ai_code_review.llm.base import ReviewResult, ReviewIssue, Severity


@pytest.fixture
def runner():
    return CliRunner()


class TestReviewCommand:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_review_staged_diff(self, mock_diff, mock_build, runner):
        mock_diff.return_value = "some diff"
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        assert result.exit_code == 0

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_exits_1_when_blocked(self, mock_diff, mock_build, runner):
        mock_diff.return_value = "some diff"
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[
            ReviewIssue(severity=Severity.CRITICAL, file="a.c", line=1, message="leak"),
        ])
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        assert result.exit_code == 1

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_no_diff_exits_clean(self, mock_diff, mock_build, runner):
        mock_diff.return_value = ""
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "no" in result.output.lower() and ("change" in result.output.lower() or "staged" in result.output.lower())


class TestCheckCommitCommand:
    def test_valid_message(self, runner):
        result = runner.invoke(main, ["check-commit"], input="[BSP-123] fix bug\n")
        assert result.exit_code == 0

    def test_invalid_message(self, runner):
        result = runner.invoke(main, ["check-commit"], input="bad message\n")
        assert result.exit_code == 1


class TestConfigCommand:
    @patch("ai_code_review.cli.Config")
    def test_config_set(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = runner.invoke(main, ["config", "set", "provider", "default", "ollama"])
        assert result.exit_code == 0
        mock_config.set.assert_called_once_with("provider", "default", "ollama")
