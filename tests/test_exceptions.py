import pytest

from ai_code_review.exceptions import (
    AIReviewError,
    ProviderNotConfiguredError,
    ProviderError,
)


class TestExceptionHierarchy:
    def test_provider_not_configured_is_ai_review_error(self):
        with pytest.raises(AIReviewError):
            raise ProviderNotConfiguredError("no provider")

    def test_provider_error_is_ai_review_error(self):
        with pytest.raises(AIReviewError):
            raise ProviderError("connection failed")

    def test_provider_not_configured_message(self):
        err = ProviderNotConfiguredError("no provider set")
        assert str(err) == "no provider set"

    def test_provider_error_message(self):
        err = ProviderError("timeout")
        assert str(err) == "timeout"
