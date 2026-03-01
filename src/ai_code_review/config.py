from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ai-code-review"
_CONFIG_FILENAME = "config.toml"

# Default extensions to review (Android BSP: C/C++/Java)
DEFAULT_INCLUDE_EXTENSIONS = "c,cpp,h,hpp,java"

# Default maximum diff lines to send to LLM (prevents context window overflow)
DEFAULT_MAX_DIFF_LINES = 2000

# Mapping of provider name to the config key that holds the env var name for its token.
_TOKEN_ENV_KEYS: dict[str, str] = {
    "openai": "api_key_env",
    "enterprise": "auth_token_env",
    "ollama": "api_key_env",
}


class Config:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or _DEFAULT_CONFIG_DIR
        self._path = self._dir / _CONFIG_FILENAME
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return tomllib.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def _save(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(tomli_w.dumps(self._data).encode())

    def get(self, section: str, key: str) -> str | None:
        return self._data.get(section, {}).get(key)

    def set(self, section: str, key: str, value: str) -> None:
        self._data.setdefault(section, {})[key] = value
        self._save()

    def resolve_provider(self, cli_provider: str | None) -> str | None:
        if cli_provider:
            return cli_provider
        return self.get("provider", "default")

    def resolve_token(self, provider: str) -> str | None:
        env_key_name = _TOKEN_ENV_KEYS.get(provider, "api_key_env")
        env_var = self.get(provider, env_key_name)
        if not env_var:
            return None
        return os.environ.get(env_var)
