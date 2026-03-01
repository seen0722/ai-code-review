import logging
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main
from ai_code_review.exceptions import ProviderNotConfiguredError
from ai_code_review.git import GitError
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
        mock_provider.health_check.return_value = (True, "Connected")
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
        mock_provider.health_check.return_value = (True, "Connected")
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


    @patch("ai_code_review.cli.get_staged_diff")
    def test_git_error_with_brackets_does_not_crash(self, mock_diff, runner):
        mock_diff.side_effect = GitError("fatal: bad object [/<m>]")
        result = runner.invoke(main, [])
        assert result.exit_code == 1
        assert "fatal: bad object" in result.output

    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_passes_custom_rules_from_config(self, mock_diff, mock_build, mock_config_cls, runner):
        mock_diff.return_value = "some diff"
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda s, k: {
            ("review", "include_extensions"): "c,cpp",
            ("review", "custom_rules"): "check integer overflow",
        }.get((s, k))
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        assert result.exit_code == 0
        prompt_arg = mock_provider.review_code.call_args[0][1]
        assert "integer overflow" in prompt_arg

    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_no_custom_rules_uses_default_prompt(self, mock_diff, mock_build, mock_config_cls, runner):
        mock_diff.return_value = "some diff"
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        assert result.exit_code == 0
        prompt_arg = mock_provider.review_code.call_args[0][1]
        assert "Additional rules" not in prompt_arg


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


class TestDiffTruncation:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    @patch("ai_code_review.cli.Config")
    def test_truncates_large_diff(self, mock_config_cls, mock_diff, mock_build, runner):
        # Create a diff with 3000 lines
        large_diff = "\n".join(f"line {i}" for i in range(3000))
        mock_diff.return_value = large_diff
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda s, k: {
            ("review", "include_extensions"): None,
            ("review", "custom_rules"): None,
            ("review", "max_diff_lines"): "2000",
        }.get((s, k))
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        # Verify the diff passed to provider is truncated
        diff_arg = mock_provider.review_code.call_args[0][0]
        assert "truncated" in diff_arg.lower()
        assert "Warning" in result.output or "truncated" in result.output.lower()

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    @patch("ai_code_review.cli.Config")
    def test_small_diff_not_truncated(self, mock_config_cls, mock_diff, mock_build, runner):
        small_diff = "\n".join(f"line {i}" for i in range(100))
        mock_diff.return_value = small_diff
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        diff_arg = mock_provider.review_code.call_args[0][0]
        assert "truncated" not in diff_arg.lower()


class TestHealthCheckCommand:
    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    def test_healthy_provider(self, mock_build, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = "ollama"
        mock_config.get.side_effect = lambda s, k: {
            ("ollama", "model"): "codellama",
        }.get((s, k))
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.health_check.return_value = (True, "Connected")
        mock_build.return_value = mock_provider

        result = runner.invoke(main, ["health-check"])
        assert result.exit_code == 0
        assert "ok" in result.output.lower() or "connected" in result.output.lower()

    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    def test_unhealthy_provider(self, mock_build, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = "ollama"
        mock_config.get.side_effect = lambda s, k: {
            ("ollama", "model"): "codellama",
        }.get((s, k))
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.health_check.return_value = (False, "Connection refused: http://localhost:11434")
        mock_build.return_value = mock_provider

        result = runner.invoke(main, ["health-check"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower() or "connection refused" in result.output.lower()

    @patch("ai_code_review.cli.Config")
    def test_no_provider_configured(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        with patch("ai_code_review.cli._build_provider", side_effect=ProviderNotConfiguredError("No provider configured")):
            result = runner.invoke(main, ["health-check"])
        assert result.exit_code == 1
        assert "no provider" in result.output.lower()


class TestConfigShowCommand:
    @patch("ai_code_review.cli.Config")
    def test_show_all_config(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config._data = {
            "provider": {"default": "openai"},
            "openai": {"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o"},
        }
        mock_config_cls.return_value = mock_config

        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "[provider]" in result.output
        assert "default = openai" in result.output
        assert "[openai]" in result.output
        assert "model = gpt-4o" in result.output

    @patch("ai_code_review.cli.Config")
    def test_show_single_section(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config._data = {
            "provider": {"default": "openai"},
            "openai": {"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o"},
        }
        mock_config_cls.return_value = mock_config

        result = runner.invoke(main, ["config", "show", "openai"])
        assert result.exit_code == 0
        assert "[openai]" in result.output
        assert "[provider]" not in result.output

    @patch("ai_code_review.cli.Config")
    def test_show_empty_config(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config._data = {}
        mock_config_cls.return_value = mock_config

        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "no configuration" in result.output.lower()

    @patch("ai_code_review.cli.Config")
    def test_show_unknown_section(self, mock_config_cls, runner):
        mock_config = MagicMock()
        mock_config._data = {"provider": {"default": "ollama"}}
        mock_config_cls.return_value = mock_config

        result = runner.invoke(main, ["config", "show", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestBuildProvider:
    def test_raises_when_no_provider(self):
        from ai_code_review.cli import _build_provider
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = None
        with pytest.raises(ProviderNotConfiguredError):
            _build_provider(mock_config, None, None)

    def test_raises_for_unknown_provider(self):
        from ai_code_review.cli import _build_provider
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = "nonexistent"
        with pytest.raises(ProviderNotConfiguredError):
            _build_provider(mock_config, None, None)


class TestVerboseFlag:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_verbose_enables_debug_logging(self, mock_diff, mock_build, runner):
        mock_diff.return_value = ""
        result = runner.invoke(main, ["-v"])
        # Check that ai_code_review logger is set to DEBUG
        logger = logging.getLogger("ai_code_review")
        assert logger.level == logging.DEBUG

    def test_no_verbose_keeps_default_logging(self, runner):
        # Reset logger level before test
        logger = logging.getLogger("ai_code_review")
        logger.setLevel(logging.WARNING)
        result = runner.invoke(main, [], input="")
        # Without -v, logger should not be DEBUG
        assert logger.level != logging.DEBUG
