# AI Code Review — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool that provides AI-powered code review and commit message enforcement for Android BSP teams, integrated via pre-commit framework.

**Architecture:** Simple flat module structure with a provider pattern for LLM backends. `click` for CLI, `rich` for terminal output, `httpx` for HTTP calls. Pre-commit framework integration via `.pre-commit-hooks.yaml`.

**Tech Stack:** Python 3.10+, click, rich, httpx, tomli/tomli-w, openai, pytest, hatchling

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/ai_code_review/__init__.py`
- Create: `src/ai_code_review/llm/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_llm/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ai-code-review"
version = "0.1.0"
description = "AI-powered code review CLI for Android BSP teams"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "rich>=13.0",
    "httpx>=0.27",
    "tomli>=2.0;python_version<'3.11'",
    "tomli-w>=1.0",
    "openai>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.0",
    "respx>=0.22",
]

[project.scripts]
ai-review = "ai_code_review.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 2: Create package init files**

`src/ai_code_review/__init__.py`:
```python
"""AI-powered code review CLI for Android BSP teams."""

__version__ = "0.1.0"
```

`src/ai_code_review/llm/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

`tests/test_llm/__init__.py`:
```python
```

**Step 3: Install in dev mode and verify**

Run: `pip install -e ".[dev]"`
Expected: Successful installation

Run: `python -c "import ai_code_review; print(ai_code_review.__version__)"`
Expected: `0.1.0`

**Step 4: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: scaffold project structure with pyproject.toml"
```

---

### Task 2: Config Module

**Files:**
- Create: `src/ai_code_review/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing tests**

`tests/test_config.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_code_review.config'`

**Step 3: Write implementation**

`src/ai_code_review/config.py`:
```python
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/config.py tests/test_config.py
git commit -m "feat: add config module with TOML read/write and provider resolution"
```

---

### Task 3: Commit Message Checker

**Files:**
- Create: `src/ai_code_review/commit_check.py`
- Create: `tests/test_commit_check.py`

**Step 1: Write the failing tests**

`tests/test_commit_check.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_commit_check.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/commit_check.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass

_COMMIT_MSG_PATTERN = re.compile(
    r"^\[[A-Z]+-\d+\] .+"
)

_FORMAT_HINT = "Expected format: [PROJECT-NUMBER] description  (e.g. [BSP-456] fix camera HAL crash)"


@dataclass(frozen=True)
class CommitCheckResult:
    valid: bool
    error: str | None = None


def check_commit_message(message: str) -> CommitCheckResult:
    message = message.strip()
    if not message:
        return CommitCheckResult(valid=False, error=f"Commit message is empty. {_FORMAT_HINT}")
    if not _COMMIT_MSG_PATTERN.match(message):
        return CommitCheckResult(valid=False, error=f"Invalid commit message format. {_FORMAT_HINT}")
    return CommitCheckResult(valid=True)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_commit_check.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/commit_check.py tests/test_commit_check.py
git commit -m "feat: add commit message format checker with [PROJECT-NUMBER] validation"
```

---

### Task 4: Git Diff Parser

**Files:**
- Create: `src/ai_code_review/git.py`
- Create: `tests/test_git.py`

**Step 1: Write the failing tests**

`tests/test_git.py`:
```python
import subprocess

import pytest

from ai_code_review.git import get_staged_diff, get_unstaged_diff, get_commit_diff, GitError


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Create a temporary git repo with an initial commit."""
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestStagedDiff:
    def test_returns_staged_changes(self, git_repo):
        (git_repo / "file.c").write_text("int main() { return 0; }")
        subprocess.run(["git", "add", "file.c"], cwd=git_repo, check=True, capture_output=True)
        diff = get_staged_diff()
        assert "file.c" in diff
        assert "int main()" in diff

    def test_empty_when_nothing_staged(self, git_repo):
        diff = get_staged_diff()
        assert diff == ""


class TestUnstagedDiff:
    def test_returns_unstaged_changes(self, git_repo):
        (git_repo / "init.txt").write_text("modified")
        diff = get_unstaged_diff()
        assert "modified" in diff


class TestCommitDiff:
    def test_returns_diff_between_commits(self, git_repo):
        (git_repo / "new.c").write_text("void foo() {}")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=git_repo, check=True, capture_output=True)
        diff = get_commit_diff("HEAD~1", "HEAD")
        assert "new.c" in diff
        assert "void foo()" in diff


class TestGitError:
    def test_raises_when_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(GitError):
            get_staged_diff()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/git.py`:
```python
from __future__ import annotations

import subprocess


class GitError(Exception):
    pass


def _run_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        raise GitError("git is not installed or not in PATH")
    return result.stdout


def get_staged_diff() -> str:
    return _run_git("diff", "--cached").strip()


def get_unstaged_diff() -> str:
    return _run_git("diff").strip()


def get_commit_diff(from_ref: str, to_ref: str) -> str:
    return _run_git("diff", from_ref, to_ref).strip()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_git.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/git.py tests/test_git.py
git commit -m "feat: add git diff parser with staged/unstaged/commit diff support"
```

---

### Task 5: LLM Provider — Base + Data Models

**Files:**
- Create: `src/ai_code_review/llm/base.py`
- Create: `tests/test_llm/test_base.py`

**Step 1: Write the failing tests**

`tests/test_llm/test_base.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/llm/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def blocks(self) -> bool:
        return self in (Severity.CRITICAL, Severity.ERROR)


@dataclass(frozen=True)
class ReviewIssue:
    severity: Severity
    file: str
    line: int
    message: str


@dataclass
class ReviewResult:
    issues: list[ReviewIssue] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return any(issue.severity.blocks for issue in self.issues)

    @property
    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts


class LLMProvider(ABC):
    @abstractmethod
    def review_code(self, diff: str, prompt: str) -> ReviewResult: ...

    @abstractmethod
    def improve_commit_msg(self, message: str, diff: str) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm/test_base.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/base.py tests/test_llm/test_base.py
git commit -m "feat: add LLM provider base class with severity levels and review data models"
```

---

### Task 6: LLM Provider — Ollama

**Files:**
- Create: `src/ai_code_review/llm/ollama.py`
- Create: `tests/test_llm/test_ollama.py`

**Step 1: Write the failing tests**

`tests/test_llm/test_ollama.py`:
```python
import json

import httpx
import pytest
import respx

from ai_code_review.llm.ollama import OllamaProvider
from ai_code_review.llm.base import Severity


@pytest.fixture
def provider():
    return OllamaProvider(base_url="http://localhost:11434", model="codellama")


class TestOllamaHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        assert provider.health_check() is True

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        assert provider.health_check() is False


class TestOllamaReviewCode:
    @respx.mock
    def test_parses_review_response(self, provider):
        llm_response = json.dumps([
            {"severity": "critical", "file": "hal.c", "line": 42, "message": "memory leak"}
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": llm_response}
            })
        )
        result = provider.review_code("diff content", "review prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.CRITICAL
        assert result.issues[0].file == "hal.c"

    @respx.mock
    def test_returns_empty_on_no_issues(self, provider):
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "[]"}
            })
        )
        result = provider.review_code("diff content", "review prompt")
        assert len(result.issues) == 0
        assert result.is_blocked is False


class TestOllamaImproveCommitMsg:
    @respx.mock
    def test_returns_improved_message(self, provider):
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "[BSP-456] fix camera HAL crash during boot sequence"}
            })
        )
        result = provider.improve_commit_msg("[BSP-456] fix camera HAL crash when boot", "diff")
        assert result == "[BSP-456] fix camera HAL crash during boot sequence"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_ollama.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/llm/ollama.py`:
```python
from __future__ import annotations

import json
import logging

import httpx

from .base import LLMProvider, ReviewIssue, ReviewResult, Severity

logger = logging.getLogger(__name__)

_REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=120.0)

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self._base_url}/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{_REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = (
            "You are a technical writing assistant. "
            "Given the original commit message and the git diff, "
            "fix English grammar and make the description more precise. "
            "Keep it under 72 characters. "
            "Preserve the [PROJECT-NUMBER] prefix. "
            "Respond with only the improved commit message, nothing else.\n\n"
            f"Original: {message}\n\nDiff:\n{diff}"
        )
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        resp = self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _parse_review(self, content: str) -> ReviewResult:
        try:
            # Strip markdown code fences if present
            text = content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            items = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM review response: %s", content[:200])
            return ReviewResult()

        issues = []
        for item in items:
            try:
                issues.append(ReviewIssue(
                    severity=Severity(item["severity"]),
                    file=item["file"],
                    line=int(item["line"]),
                    message=item["message"],
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed issue: %s (%s)", item, e)
        return ReviewResult(issues=issues)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm/test_ollama.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/ollama.py tests/test_llm/test_ollama.py
git commit -m "feat: add Ollama LLM provider"
```

---

### Task 7: LLM Provider — OpenAI

**Files:**
- Create: `src/ai_code_review/llm/openai.py`
- Create: `tests/test_llm/test_openai.py`

**Step 1: Write the failing tests**

`tests/test_llm/test_openai.py`:
```python
import json
from unittest.mock import MagicMock, patch

import pytest

from ai_code_review.llm.openai import OpenAIProvider
from ai_code_review.llm.base import Severity


@pytest.fixture
def provider():
    return OpenAIProvider(api_key="sk-test", model="gpt-4o")


@pytest.fixture
def mock_openai_response():
    """Helper to create a mock OpenAI ChatCompletion response."""
    def _make(content: str):
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response
    return _make


class TestOpenAIReviewCode:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_parses_review_response(self, mock_cls, provider, mock_openai_response):
        issues_json = json.dumps([
            {"severity": "error", "file": "driver.c", "line": 10, "message": "null deref"}
        ])
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(issues_json)
        provider._client = mock_cls.return_value

        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.ERROR


class TestOpenAIImproveCommitMsg:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_returns_improved_message(self, mock_cls, provider, mock_openai_response):
        mock_cls.return_value.chat.completions.create.return_value = mock_openai_response(
            "[BSP-456] fix camera HAL crash during boot sequence"
        )
        provider._client = mock_cls.return_value

        result = provider.improve_commit_msg("[BSP-456] fix crash when boot", "diff")
        assert result == "[BSP-456] fix camera HAL crash during boot sequence"


class TestOpenAIHealthCheck:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_healthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.return_value = []
        provider._client = mock_cls.return_value
        assert provider.health_check() is True

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_unhealthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.side_effect = Exception("connection refused")
        provider._client = mock_cls.return_value
        assert provider.health_check() is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_openai.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/llm/openai.py`:
```python
from __future__ import annotations

import json
import logging

from openai import OpenAI

from .base import LLMProvider, ReviewIssue, ReviewResult, Severity

logger = logging.getLogger(__name__)

_REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def health_check(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{_REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = (
            "You are a technical writing assistant. "
            "Given the original commit message and the git diff, "
            "fix English grammar and make the description more precise. "
            "Keep it under 72 characters. "
            "Preserve the [PROJECT-NUMBER] prefix. "
            "Respond with only the improved commit message, nothing else.\n\n"
            f"Original: {message}\n\nDiff:\n{diff}"
        )
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _parse_review(self, content: str) -> ReviewResult:
        try:
            text = content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            items = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM review response: %s", content[:200])
            return ReviewResult()

        issues = []
        for item in items:
            try:
                issues.append(ReviewIssue(
                    severity=Severity(item["severity"]),
                    file=item["file"],
                    line=int(item["line"]),
                    message=item["message"],
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed issue: %s (%s)", item, e)
        return ReviewResult(issues=issues)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm/test_openai.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/openai.py tests/test_llm/test_openai.py
git commit -m "feat: add OpenAI LLM provider"
```

---

### Task 8: LLM Provider — Enterprise

**Files:**
- Create: `src/ai_code_review/llm/enterprise.py`
- Create: `tests/test_llm/test_enterprise.py`

**Step 1: Write the failing tests**

`tests/test_llm/test_enterprise.py`:
```python
import json

import httpx
import pytest
import respx

from ai_code_review.llm.enterprise import EnterpriseProvider
from ai_code_review.llm.base import Severity


@pytest.fixture
def provider():
    return EnterpriseProvider(
        base_url="https://llm.internal.company.com",
        api_path="/v1/chat/completions",
        model="internal-codellama-70b",
        auth_type="bearer",
        auth_token="test-token",
    )


class TestEnterpriseHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        assert provider.health_check() is True

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            side_effect=httpx.ConnectError("refused")
        )
        assert provider.health_check() is False


class TestEnterpriseReviewCode:
    @respx.mock
    def test_parses_response(self, provider):
        issues_json = json.dumps([
            {"severity": "warning", "file": "hal.c", "line": 5, "message": "hardcoded password"}
        ])
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": issues_json}}]
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING

    @respx.mock
    def test_sends_bearer_auth(self, provider):
        route = respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "[]"}}]
            })
        )
        provider.review_code("diff", "prompt")
        assert route.calls[0].request.headers["Authorization"] == "Bearer test-token"


class TestEnterpriseImproveCommitMsg:
    @respx.mock
    def test_returns_improved_message(self, provider):
        respx.post("https://llm.internal.company.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "choices": [{"message": {"content": "[BSP-1] improved message"}}]
            })
        )
        result = provider.improve_commit_msg("[BSP-1] bad msg", "diff")
        assert result == "[BSP-1] improved message"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_enterprise.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/llm/enterprise.py`:
```python
from __future__ import annotations

import json
import logging

import httpx

from .base import LLMProvider, ReviewIssue, ReviewResult, Severity

logger = logging.getLogger(__name__)

_REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""


class EnterpriseProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_path: str,
        model: str,
        auth_type: str = "bearer",
        auth_token: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_path = api_path
        self._model = model
        self._headers = self._build_auth_headers(auth_type, auth_token)
        self._client = httpx.Client(timeout=120.0, headers=self._headers)

    @staticmethod
    def _build_auth_headers(auth_type: str, token: str) -> dict[str, str]:
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {token}"}
        elif auth_type == "api-key":
            return {"X-API-Key": token}
        else:
            return {"Authorization": token}

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self._base_url}/v1/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def review_code(self, diff: str, prompt: str) -> ReviewResult:
        full_prompt = f"{prompt}\n\n{_REVIEW_RESPONSE_SCHEMA}\n\nDiff:\n{diff}"
        content = self._chat(full_prompt)
        return self._parse_review(content)

    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = (
            "You are a technical writing assistant. "
            "Given the original commit message and the git diff, "
            "fix English grammar and make the description more precise. "
            "Keep it under 72 characters. "
            "Preserve the [PROJECT-NUMBER] prefix. "
            "Respond with only the improved commit message, nothing else.\n\n"
            f"Original: {message}\n\nDiff:\n{diff}"
        )
        return self._chat(prompt).strip()

    def _chat(self, prompt: str) -> str:
        resp = self._client.post(
            f"{self._base_url}{self._api_path}",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _parse_review(self, content: str) -> ReviewResult:
        try:
            text = content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            items = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM review response: %s", content[:200])
            return ReviewResult()

        issues = []
        for item in items:
            try:
                issues.append(ReviewIssue(
                    severity=Severity(item["severity"]),
                    file=item["file"],
                    line=int(item["line"]),
                    message=item["message"],
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed issue: %s (%s)", item, e)
        return ReviewResult(issues=issues)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm/test_enterprise.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/enterprise.py tests/test_llm/test_enterprise.py
git commit -m "feat: add Enterprise LLM provider with configurable auth"
```

---

### Task 9: Prompts Module

**Files:**
- Create: `src/ai_code_review/prompts.py`
- Create: `tests/test_prompts.py`

**Step 1: Write the failing tests**

`tests/test_prompts.py`:
```python
from ai_code_review.prompts import get_review_prompt, get_commit_improve_prompt


class TestReviewPrompt:
    def test_contains_bsp_focus_areas(self):
        prompt = get_review_prompt()
        assert "memory leak" in prompt.lower()
        assert "null pointer" in prompt.lower()
        assert "race condition" in prompt.lower()

    def test_excludes_style_review(self):
        prompt = get_review_prompt()
        assert "naming" not in prompt.lower() or "do not" in prompt.lower()


class TestCommitImprovePrompt:
    def test_contains_grammar_instruction(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "diff content")
        assert "grammar" in prompt.lower()

    def test_contains_original_message(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "diff content")
        assert "[BSP-1] fix bug" in prompt

    def test_contains_diff(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "some diff here")
        assert "some diff here" in prompt
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/prompts.py`:
```python
from __future__ import annotations

_REVIEW_PROMPT = """\
You are a senior Android BSP engineer. Review the following git diff and report only serious issues.

Focus on:
- Memory leaks (malloc without free, unreleased resources)
- Null pointer dereference
- Race conditions, missing lock/mutex protection
- Hardcoded secrets (keys, passwords, tokens)
- Obvious logic errors
- Buffer overflow

Do not report:
- Code style or naming suggestions
- Performance optimization suggestions
- Refactoring suggestions

Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""

_COMMIT_IMPROVE_PROMPT = """\
You are a technical writing assistant. Given the original commit message and the git diff:
1. Fix English grammar errors
2. Make the description accurately reflect the code changes
3. Keep it under 72 characters total
4. Preserve the [PROJECT-NUMBER] prefix exactly as-is

Respond with only the improved commit message. No explanation, no quotes.

Original: {message}

Diff:
{diff}"""


def get_review_prompt() -> str:
    return _REVIEW_PROMPT


def get_commit_improve_prompt(message: str, diff: str) -> str:
    return _COMMIT_IMPROVE_PROMPT.format(message=message, diff=diff)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompts.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/prompts.py tests/test_prompts.py
git commit -m "feat: add review and commit message improvement prompt templates"
```

---

### Task 10: Output Formatters

**Files:**
- Create: `src/ai_code_review/formatters.py`
- Create: `tests/test_formatters.py`

**Step 1: Write the failing tests**

`tests/test_formatters.py`:
```python
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_formatters.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/formatters.py`:
```python
from __future__ import annotations

import json

from rich.console import Console
from rich.text import Text

from .llm.base import ReviewResult, Severity

_SEVERITY_ICONS = {
    Severity.CRITICAL: "\u274c",
    Severity.ERROR: "\u274c",
    Severity.WARNING: "\u26a0\ufe0f",
    Severity.INFO: "\u2139\ufe0f",
}

_SEVERITY_STYLES = {
    Severity.CRITICAL: "bold red",
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}


def format_terminal(result: ReviewResult) -> str:
    console = Console(record=True, force_terminal=True)

    if not result.issues:
        console.print("\n[bold green]\u2705 No issues found — code looks clean![/]")
        return console.export_text()

    console.print(f"\n[bold]\U0001f50d AI Code Review — {len(result.issues)} issue(s) found[/]\n")
    for issue in result.issues:
        icon = _SEVERITY_ICONS[issue.severity]
        style = _SEVERITY_STYLES[issue.severity]
        console.print(
            f"  {icon} [{style}][{issue.severity.value}][/] "
            f"[bold]{issue.file}:{issue.line}[/]"
        )
        console.print(f"     {issue.message}\n")

    summary = result.summary
    parts = [f"{count} {name}" for name, count in summary.items() if count > 0]
    console.print(f"[dim]{'─' * 50}[/]")
    console.print(f"Summary: {', '.join(parts)}")

    if result.is_blocked:
        console.print("[bold red]\u274c Commit blocked (critical/error found)[/]")
    else:
        console.print("[bold green]\u2705 Commit allowed (warnings only)[/]")

    return console.export_text()


def format_markdown(result: ReviewResult) -> str:
    lines = ["# AI Code Review Report\n"]
    if not result.issues:
        lines.append("No issues found.\n")
        return "\n".join(lines)

    lines.append("| Severity | File | Line | Issue |")
    lines.append("|----------|------|------|-------|")
    for issue in result.issues:
        lines.append(f"| {issue.severity.value} | {issue.file} | {issue.line} | {issue.message} |")

    summary = result.summary
    parts = [f"{count} {name}" for name, count in summary.items() if count > 0]
    lines.append(f"\n**Summary:** {', '.join(parts)}")
    lines.append(f"**Blocked:** {'Yes' if result.is_blocked else 'No'}")
    return "\n".join(lines)


def format_json(result: ReviewResult) -> str:
    data = {
        "summary": result.summary,
        "blocked": result.is_blocked,
        "issues": [
            {
                "severity": issue.severity.value,
                "file": issue.file,
                "line": issue.line,
                "message": issue.message,
            }
            for issue in result.issues
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_formatters.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/formatters.py tests/test_formatters.py
git commit -m "feat: add terminal, markdown, and JSON output formatters"
```

---

### Task 11: Reviewer Orchestrator

**Files:**
- Create: `src/ai_code_review/reviewer.py`
- Create: `tests/test_reviewer.py`

**Step 1: Write the failing tests**

`tests/test_reviewer.py`:
```python
from unittest.mock import MagicMock

import pytest

from ai_code_review.reviewer import Reviewer
from ai_code_review.llm.base import ReviewResult, ReviewIssue, Severity


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.review_code.return_value = ReviewResult(issues=[
        ReviewIssue(severity=Severity.WARNING, file="a.c", line=1, message="minor"),
    ])
    provider.improve_commit_msg.return_value = "[BSP-1] improved message"
    provider.health_check.return_value = True
    return provider


@pytest.fixture
def reviewer(mock_provider):
    return Reviewer(provider=mock_provider)


class TestReviewDiff:
    def test_calls_provider_with_diff(self, reviewer, mock_provider):
        reviewer.review_diff("some diff content")
        mock_provider.review_code.assert_called_once()
        args = mock_provider.review_code.call_args
        assert "some diff content" in args[0]

    def test_returns_review_result(self, reviewer):
        result = reviewer.review_diff("diff")
        assert isinstance(result, ReviewResult)
        assert len(result.issues) == 1


class TestImproveCommitMessage:
    def test_calls_provider(self, reviewer, mock_provider):
        reviewer.improve_commit_message("[BSP-1] fix bug", "diff")
        mock_provider.improve_commit_msg.assert_called_once_with("[BSP-1] fix bug", "diff")

    def test_returns_improved_message(self, reviewer):
        result = reviewer.improve_commit_message("[BSP-1] fix bug", "diff")
        assert result == "[BSP-1] improved message"


class TestHealthCheck:
    def test_delegates_to_provider(self, reviewer, mock_provider):
        assert reviewer.check_provider_health() is True
        mock_provider.health_check.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reviewer.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/reviewer.py`:
```python
from __future__ import annotations

from .llm.base import LLMProvider, ReviewResult
from .prompts import get_review_prompt


class Reviewer:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def review_diff(self, diff: str) -> ReviewResult:
        prompt = get_review_prompt()
        return self._provider.review_code(diff, prompt)

    def improve_commit_message(self, message: str, diff: str) -> str:
        return self._provider.improve_commit_msg(message, diff)

    def check_provider_health(self) -> bool:
        return self._provider.health_check()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reviewer.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/reviewer.py tests/test_reviewer.py
git commit -m "feat: add reviewer orchestrator"
```

---

### Task 12: CLI — Main Commands

**Files:**
- Create: `src/ai_code_review/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
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
        assert "no changes" in result.output.lower() or "no staged" in result.output.lower()


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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

`src/ai_code_review/cli.py`:
```python
from __future__ import annotations

import sys

import click
from rich.console import Console

from .commit_check import check_commit_message
from .config import Config
from .formatters import format_json, format_markdown, format_terminal
from .git import GitError, get_staged_diff
from .llm.base import LLMProvider
from .llm.enterprise import EnterpriseProvider
from .llm.ollama import OllamaProvider
from .llm.openai import OpenAIProvider
from .reviewer import Reviewer

console = Console()


def _build_provider(config: Config, cli_provider: str | None, cli_model: str | None) -> LLMProvider:
    provider_name = config.resolve_provider(cli_provider)
    if not provider_name:
        console.print("[bold red]No provider configured. Run: ai-review config set provider default <name>[/]")
        sys.exit(1)

    if provider_name == "ollama":
        base_url = config.get("ollama", "base_url") or "http://localhost:11434"
        model = cli_model or config.get("ollama", "model") or "codellama"
        return OllamaProvider(base_url=base_url, model=model)

    elif provider_name == "openai":
        token = config.resolve_token("openai")
        if not token:
            console.print("[bold red]OpenAI API key not found. Set the env var specified in config.[/]")
            sys.exit(1)
        model = cli_model or config.get("openai", "model") or "gpt-4o"
        base_url = config.get("openai", "base_url")
        return OpenAIProvider(api_key=token, model=model, base_url=base_url)

    elif provider_name == "enterprise":
        token = config.resolve_token("enterprise") or ""
        base_url = config.get("enterprise", "base_url")
        if not base_url:
            console.print("[bold red]Enterprise base_url not configured.[/]")
            sys.exit(1)
        api_path = config.get("enterprise", "api_path") or "/v1/chat/completions"
        model = cli_model or config.get("enterprise", "model") or "default"
        auth_type = config.get("enterprise", "auth_type") or "bearer"
        return EnterpriseProvider(
            base_url=base_url, api_path=api_path, model=model,
            auth_type=auth_type, auth_token=token,
        )

    console.print(f"[bold red]Unknown provider: {provider_name}[/]")
    sys.exit(1)


@click.group(invoke_without_command=True)
@click.option("--provider", "cli_provider", default=None, help="LLM provider (ollama/openai/enterprise)")
@click.option("--model", "cli_model", default=None, help="Model name")
@click.option("--format", "output_format", default="terminal", type=click.Choice(["terminal", "markdown", "json"]))
@click.pass_context
def main(ctx: click.Context, cli_provider: str | None, cli_model: str | None, output_format: str) -> None:
    """AI-powered code review for Android BSP teams."""
    ctx.ensure_object(dict)
    ctx.obj["cli_provider"] = cli_provider
    ctx.obj["cli_model"] = cli_model
    ctx.obj["output_format"] = output_format

    if ctx.invoked_subcommand is None:
        _review(ctx)


def _review(ctx: click.Context) -> None:
    config = Config()
    cli_provider = ctx.obj["cli_provider"]
    cli_model = ctx.obj["cli_model"]
    output_format = ctx.obj["output_format"]

    try:
        diff = get_staged_diff()
    except GitError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)

    if not diff:
        console.print("[dim]No staged changes to review.[/]")
        return

    provider = _build_provider(config, cli_provider, cli_model)
    reviewer = Reviewer(provider=provider)
    result = reviewer.review_diff(diff)

    formatters = {"terminal": format_terminal, "markdown": format_markdown, "json": format_json}
    output = formatters[output_format](result)
    click.echo(output)

    if result.is_blocked:
        sys.exit(1)


@main.command("check-commit")
@click.argument("message_file", required=False)
def check_commit(message_file: str | None) -> None:
    """Check commit message format. Reads from file path (for git hook) or stdin."""
    if message_file:
        with open(message_file) as f:
            message = f.read().strip()
    else:
        message = click.get_text_stream("stdin").readline().strip()

    result = check_commit_message(message)
    if not result.valid:
        console.print(f"[bold red]{result.error}[/]")
        sys.exit(1)
    console.print("[green]Commit message format OK.[/]")


@main.group("config")
def config_group() -> None:
    """Manage configuration."""
    pass


@config_group.command("set")
@click.argument("section")
@click.argument("key")
@click.argument("value")
def config_set(section: str, key: str, value: str) -> None:
    """Set a config value: ai-review config set <section> <key> <value>"""
    config = Config()
    config.set(section, key, value)
    console.print(f"[green]Set {section}.{key} = {value}[/]")


@config_group.command("get")
@click.argument("section")
@click.argument("key")
def config_get(section: str, key: str) -> None:
    """Get a config value: ai-review config get <section> <key>"""
    config = Config()
    value = config.get(section, key)
    if value is None:
        console.print(f"[dim]{section}.{key} is not set[/]")
    else:
        console.print(value)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add CLI with review, check-commit, and config commands"
```

---

### Task 13: Hook Management + Pre-commit Integration

**Files:**
- Create: `.pre-commit-hooks.yaml`
- Modify: `src/ai_code_review/cli.py` (add `hook` subcommand group)
- Create: `tests/test_hooks.py`

**Step 1: Create .pre-commit-hooks.yaml**

`.pre-commit-hooks.yaml`:
```yaml
- id: ai-review-commit-msg
  name: Check commit message format
  entry: ai-review check-commit
  language: python
  stages: [commit-msg]
  always_run: true

- id: ai-review-code
  name: AI Code Review
  entry: ai-review
  language: python
  stages: [pre-commit]
  pass_filenames: false
```

**Step 2: Write the failing tests for hook commands**

`tests/test_hooks.py`:
```python
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestHookInstall:
    def test_installs_pre_commit_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "pre-commit"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists()
        assert "ai-review" in hook_path.read_text()

    def test_installs_commit_msg_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "commit-msg"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "commit-msg"
        assert hook_path.exists()
        assert "ai-review" in hook_path.read_text()


class TestHookUninstall:
    def test_removes_hook(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "uninstall", "pre-commit"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        assert not hook_path.exists()


class TestHookStatus:
    def test_shows_installed_hooks(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "pre-commit" in result.output
        assert "installed" in result.output.lower()
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_hooks.py -v`
Expected: FAIL — no `hook` command

**Step 4: Add hook commands to cli.py**

Append to `src/ai_code_review/cli.py`:
```python
_HOOK_SCRIPT_TEMPLATE = """#!/bin/sh
# Installed by ai-code-review
{command}
"""

_HOOK_COMMANDS = {
    "pre-commit": 'ai-review "$@"',
    "commit-msg": 'ai-review check-commit "$1"',
}


@main.group("hook")
def hook_group() -> None:
    """Manage git hooks."""
    pass


@hook_group.command("install")
@click.argument("hook_type", type=click.Choice(list(_HOOK_COMMANDS.keys())))
def hook_install(hook_type: str) -> None:
    """Install a git hook."""
    hooks_dir = _get_hooks_dir()
    hook_path = hooks_dir / hook_type
    script = _HOOK_SCRIPT_TEMPLATE.format(command=_HOOK_COMMANDS[hook_type])
    hook_path.write_text(script)
    hook_path.chmod(0o755)
    console.print(f"[green]Installed {hook_type} hook.[/]")


@hook_group.command("uninstall")
@click.argument("hook_type", type=click.Choice(list(_HOOK_COMMANDS.keys())))
def hook_uninstall(hook_type: str) -> None:
    """Uninstall a git hook."""
    hooks_dir = _get_hooks_dir()
    hook_path = hooks_dir / hook_type
    if hook_path.exists():
        hook_path.unlink()
        console.print(f"[green]Removed {hook_type} hook.[/]")
    else:
        console.print(f"[dim]{hook_type} hook is not installed.[/]")


@hook_group.command("status")
def hook_status() -> None:
    """Show installed hooks."""
    hooks_dir = _get_hooks_dir()
    for hook_type in _HOOK_COMMANDS:
        hook_path = hooks_dir / hook_type
        if hook_path.exists() and "ai-review" in hook_path.read_text():
            console.print(f"  [green]{hook_type}: installed[/]")
        else:
            console.print(f"  [dim]{hook_type}: not installed[/]")


def _get_hooks_dir() -> Path:
    from pathlib import Path
    try:
        from .git import _run_git
        git_dir = _run_git("rev-parse", "--git-dir").strip()
        hooks_dir = Path(git_dir) / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        return hooks_dir
    except Exception:
        console.print("[bold red]Not in a git repository.[/]")
        sys.exit(1)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_hooks.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add .pre-commit-hooks.yaml src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add hook management commands and .pre-commit-hooks.yaml"
```

---

### Task 14: Integration — Commit Message AI Improvement Flow

**Files:**
- Modify: `src/ai_code_review/cli.py` (enhance `check-commit` to include AI improvement)
- Create: `tests/test_commit_flow.py`

**Step 1: Write the failing tests**

`tests/test_commit_flow.py`:
```python
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
    def test_suggests_improved_message(self, mock_build, runner, tmp_path):
        mock_provider = MagicMock()
        mock_provider.improve_commit_msg.return_value = "[BSP-456] fix camera HAL crash during boot sequence"
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider

        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-456] fix camera HAL crash when boot")

        # Simulate user accepting the suggestion
        result = runner.invoke(main, ["check-commit", str(msg_file)], input="a\n")
        assert result.exit_code == 0
        assert "fix camera HAL crash during boot sequence" in result.output

    @patch("ai_code_review.cli._build_provider")
    def test_skip_keeps_original(self, mock_build, runner, tmp_path):
        mock_provider = MagicMock()
        mock_provider.improve_commit_msg.return_value = "[BSP-456] improved"
        mock_provider.health_check.return_value = True
        mock_build.return_value = mock_provider

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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_commit_flow.py -v`
Expected: FAIL — current `check-commit` doesn't have AI improvement

**Step 3: Update check-commit in cli.py**

Replace the `check_commit` function in `src/ai_code_review/cli.py`:
```python
@main.command("check-commit")
@click.argument("message_file", required=False)
@click.pass_context
def check_commit(ctx: click.Context, message_file: str | None) -> None:
    """Check commit message format and optionally improve with AI."""
    if message_file:
        msg_path = Path(message_file)
        message = msg_path.read_text().strip()
    else:
        message = click.get_text_stream("stdin").readline().strip()
        msg_path = None

    # Step 1: Format check
    result = check_commit_message(message)
    if not result.valid:
        console.print(f"[bold red]{result.error}[/]")
        sys.exit(1)
    console.print("[green]Commit message format OK.[/]")

    # Step 2: AI improvement (only when we have a file to update and a provider)
    if msg_path is None:
        return

    try:
        config = Config()
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config, cli_provider, cli_model)
    except SystemExit:
        # No provider configured — skip AI improvement silently
        return

    try:
        diff = get_staged_diff()
    except GitError:
        diff = ""

    if not diff:
        return

    reviewer = Reviewer(provider=provider)
    improved = reviewer.improve_commit_message(message, diff)

    if improved and improved.strip() != message:
        console.print(f"\n[dim]Original:[/]  {message}")
        console.print(f"[bold]Suggested:[/] {improved}")
        choice = click.prompt(
            "[A]ccept / [E]dit / [S]kip",
            type=click.Choice(["a", "e", "s"], case_sensitive=False),
            default="a",
        )
        if choice == "a":
            msg_path.write_text(improved + "\n")
            console.print("[green]Commit message updated.[/]")
        elif choice == "e":
            edited = click.edit(improved)
            if edited:
                msg_path.write_text(edited)
                console.print("[green]Commit message updated.[/]")
        # "s" → do nothing, keep original
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_commit_flow.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_commit_flow.py
git commit -m "feat: add AI-powered commit message improvement to check-commit flow"
```

---

### Task 15: Final Integration + README

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

**Step 1: Create README.md**

See design doc for content. Include: installation, quick start, provider config, pre-commit setup, CLI usage.

**Step 2: Create CLAUDE.md**

Based on the final project structure and conventions established during implementation.

**Step 3: Run full test suite one final time**

Run: `pytest -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add README and CLAUDE.md"
```
