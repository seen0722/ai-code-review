import pytest

from ai_code_review.commit_check import check_commit_message, CommitCheckResult


class TestValidMessages:
    @pytest.mark.parametrize("msg", [
        "[BSP-456] fix camera HAL crash on boot",
        "[KERN-1] update device tree",
        "[AUD-9999] resolve ALSA mixer issue",
        "[WIFI-12] add support for new chipset",
    ])
    def test_valid_format(self, msg):
        result = check_commit_message(msg)
        assert result.valid is True
        assert result.error is None


class TestInvalidMessages:
    def test_missing_prefix(self):
        result = check_commit_message("fix camera crash")
        assert result.valid is False
        assert "format" in result.error.lower()

    def test_missing_number(self):
        result = check_commit_message("[BSP] fix camera crash")
        assert result.valid is False

    def test_missing_description(self):
        result = check_commit_message("[BSP-456]")
        assert result.valid is False

    def test_missing_space_after_bracket(self):
        result = check_commit_message("[BSP-456]fix camera crash")
        assert result.valid is False

    def test_empty_message(self):
        result = check_commit_message("")
        assert result.valid is False

    def test_lowercase_project(self):
        result = check_commit_message("[bsp-456] fix camera crash")
        assert result.valid is False


class TestCommitCheckResult:
    def test_result_contains_expected_format_hint(self):
        result = check_commit_message("bad message")
        assert "[PROJECT-NUMBER]" in result.error
