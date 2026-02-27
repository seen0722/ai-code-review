import pytest

from ai_code_review.llm.base import LLMProvider, ReviewResult, ReviewIssue, Severity


class TestSeverity:
    def test_critical_blocks(self):
        assert Severity.CRITICAL.blocks is True

    def test_error_blocks(self):
        assert Severity.ERROR.blocks is True

    def test_warning_does_not_block(self):
        assert Severity.WARNING.blocks is False

    def test_info_does_not_block(self):
        assert Severity.INFO.blocks is False


class TestReviewResult:
    def test_is_blocked_with_critical(self):
        result = ReviewResult(issues=[
            ReviewIssue(severity=Severity.CRITICAL, file="a.c", line=1, message="leak"),
        ])
        assert result.is_blocked is True

    def test_is_not_blocked_with_only_warnings(self):
        result = ReviewResult(issues=[
            ReviewIssue(severity=Severity.WARNING, file="a.c", line=1, message="minor"),
        ])
        assert result.is_blocked is False

    def test_empty_issues_not_blocked(self):
        result = ReviewResult(issues=[])
        assert result.is_blocked is False

    def test_summary_counts(self):
        result = ReviewResult(issues=[
            ReviewIssue(severity=Severity.CRITICAL, file="a.c", line=1, message="x"),
            ReviewIssue(severity=Severity.WARNING, file="b.c", line=2, message="y"),
            ReviewIssue(severity=Severity.WARNING, file="c.c", line=3, message="z"),
        ])
        assert result.summary == {"critical": 1, "error": 0, "warning": 2, "info": 0}


class TestLLMProviderIsAbstract:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LLMProvider()
