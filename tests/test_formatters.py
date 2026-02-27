import json

import pytest

from ai_code_review.formatters import format_terminal, format_markdown, format_json
from ai_code_review.llm.base import ReviewResult, ReviewIssue, Severity


@pytest.fixture
def sample_result():
    return ReviewResult(issues=[
        ReviewIssue(severity=Severity.CRITICAL, file="hal.c", line=42, message="memory leak"),
        ReviewIssue(severity=Severity.WARNING, file="util.c", line=10, message="hardcoded value"),
    ])


@pytest.fixture
def empty_result():
    return ReviewResult(issues=[])


class TestTerminalFormatter:
    def test_contains_issue_info(self, sample_result):
        output = format_terminal(sample_result)
        assert "hal.c" in output
        assert "42" in output
        assert "memory leak" in output

    def test_shows_blocked_message(self, sample_result):
        output = format_terminal(sample_result)
        assert "blocked" in output.lower() or "block" in output.lower()

    def test_empty_result_shows_clean(self, empty_result):
        output = format_terminal(empty_result)
        assert "no issues" in output.lower() or "clean" in output.lower()


class TestMarkdownFormatter:
    def test_contains_table_headers(self, sample_result):
        output = format_markdown(sample_result)
        assert "Severity" in output
        assert "File" in output
        assert "Line" in output

    def test_contains_issue_data(self, sample_result):
        output = format_markdown(sample_result)
        assert "hal.c" in output
        assert "memory leak" in output


class TestJsonFormatter:
    def test_valid_json(self, sample_result):
        output = format_json(sample_result)
        data = json.loads(output)
        assert "summary" in data
        assert "issues" in data
        assert "blocked" in data

    def test_issue_structure(self, sample_result):
        data = json.loads(format_json(sample_result))
        assert data["blocked"] is True
        assert data["summary"]["critical"] == 1
        assert data["summary"]["warning"] == 1
        assert len(data["issues"]) == 2

    def test_empty_result(self, empty_result):
        data = json.loads(format_json(empty_result))
        assert data["blocked"] is False
        assert len(data["issues"]) == 0
