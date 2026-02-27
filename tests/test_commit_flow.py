from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestCommitMsgImprovement:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_suggests_improved_message(self, mock_diff, mock_build, runner, tmp_path):
        mock_provider = MagicMock()
        mock_provider.improve_commit_msg.return_value = "[BSP-456] fix camera HAL crash during boot sequence"
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider
        mock_diff.return_value = "some diff content"

        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-456] fix camera HAL crash when boot")

        # Simulate user accepting the suggestion
        result = runner.invoke(main, ["check-commit", str(msg_file)], input="a\n")
        assert result.exit_code == 0
        assert "fix camera HAL crash during boot sequence" in result.output

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_skip_keeps_original(self, mock_diff, mock_build, runner, tmp_path):
        mock_provider = MagicMock()
        mock_provider.improve_commit_msg.return_value = "[BSP-456] improved"
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider
        mock_diff.return_value = "some diff"

        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-456] original message")

        result = runner.invoke(main, ["check-commit", str(msg_file)], input="s\n")
        assert result.exit_code == 0
        # File should remain unchanged
        assert msg_file.read_text() == "[BSP-456] original message"

    def test_invalid_format_blocks_before_ai(self, runner, tmp_path):
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("bad message format")

        result = runner.invoke(main, ["check-commit", str(msg_file)])
        assert result.exit_code == 1
