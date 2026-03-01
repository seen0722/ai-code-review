from __future__ import annotations


class AIReviewError(Exception):
    """Base exception for ai-code-review."""


class ProviderNotConfiguredError(AIReviewError):
    """No LLM provider configured."""


class ProviderError(AIReviewError):
    """LLM provider failed (connection, auth, response)."""
