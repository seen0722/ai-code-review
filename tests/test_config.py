import os
from pathlib import Path

import pytest

from ai_code_review.config import Config


@pytest.fixture
def tmp_config(tmp_path):
    """Create a Config instance with a temporary config directory."""
    return Config(config_dir=tmp_path)


class TestConfigDefaults:
    def test_default_provider_is_none(self, tmp_config):
        assert tmp_config.get("provider", "default") is None

    def test_get_missing_key_returns_none(self, tmp_config):
        assert tmp_config.get("nonexistent", "key") is None


class TestConfigSetGet:
    def test_set_and_get_value(self, tmp_config):
        tmp_config.set("provider", "default", "ollama")
        assert tmp_config.get("provider", "default") == "ollama"

    def test_set_nested_value(self, tmp_config):
        tmp_config.set("ollama", "base_url", "http://localhost:11434")
        assert tmp_config.get("ollama", "base_url") == "http://localhost:11434"

    def test_config_persists_to_file(self, tmp_config, tmp_path):
        tmp_config.set("provider", "default", "openai")
        # Reload from same directory
        reloaded = Config(config_dir=tmp_path)
        assert reloaded.get("provider", "default") == "openai"


class TestConfigResolveProvider:
    def test_cli_flag_takes_priority(self, tmp_config):
        tmp_config.set("provider", "default", "ollama")
        assert tmp_config.resolve_provider(cli_provider="openai") == "openai"

    def test_falls_back_to_config_default(self, tmp_config):
        tmp_config.set("provider", "default", "enterprise")
        assert tmp_config.resolve_provider(cli_provider=None) == "enterprise"

    def test_returns_none_when_no_provider(self, tmp_config):
        assert tmp_config.resolve_provider(cli_provider=None) is None


class TestConfigResolveToken:
    def test_reads_token_from_env(self, tmp_config, monkeypatch):
        tmp_config.set("openai", "api_key_env", "MY_OPENAI_KEY")
        monkeypatch.setenv("MY_OPENAI_KEY", "sk-test-123")
        assert tmp_config.resolve_token("openai") == "sk-test-123"

    def test_returns_none_when_env_not_set(self, tmp_config):
        tmp_config.set("openai", "api_key_env", "MISSING_KEY")
        assert tmp_config.resolve_token("openai") is None

    def test_enterprise_uses_auth_token_env(self, tmp_config, monkeypatch):
        tmp_config.set("enterprise", "auth_token_env", "CORP_LLM_TOKEN")
        monkeypatch.setenv("CORP_LLM_TOKEN", "bearer-xyz")
        assert tmp_config.resolve_token("enterprise") == "bearer-xyz"
