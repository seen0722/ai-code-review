# Quality, UX & Reliability Optimization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate code duplication across providers, improve CLI UX with new commands, and add reliability features (retry, timeout, diff limits).

**Architecture:** Refactor shared logic into base class and prompts module first, then build new features on the cleaned-up foundation. Exception hierarchy replaces sys.exit() control flow. TDD for all new features.

**Tech Stack:** Python 3.10+, click, httpx, rich, respx (testing), pytest

---

### Task 1: Create custom exception hierarchy

**Files:**
- Create: `src/ai_code_review/exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write the test**

```python
# tests/test_exceptions.py
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ai_code_review.exceptions'`

**Step 3: Write minimal implementation**

```python
# src/ai_code_review/exceptions.py
from __future__ import annotations


class AIReviewError(Exception):
    """Base exception for ai-code-review."""


class ProviderNotConfiguredError(AIReviewError):
    """No LLM provider configured."""


class ProviderError(AIReviewError):
    """LLM provider failed (connection, auth, response)."""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_exceptions.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/ai_code_review/exceptions.py tests/test_exceptions.py
git commit -m "feat: add custom exception hierarchy (AIReviewError, ProviderNotConfiguredError, ProviderError)"
```

---

### Task 2: Extract `_parse_review()` to base class

This is a refactoring task. Existing provider tests already cover `_parse_review()` behavior.

**Files:**
- Modify: `src/ai_code_review/llm/base.py` — add `_parse_review()` method with json import
- Modify: `src/ai_code_review/llm/ollama.py` — remove `_parse_review()`, remove `json` import
- Modify: `src/ai_code_review/llm/openai.py` — remove `_parse_review()`, remove `json` import
- Modify: `src/ai_code_review/llm/enterprise.py` — remove `_parse_review()`, remove `json` import

**Step 1: Verify all existing tests pass before refactoring**

Run: `pytest tests/test_llm/ -v`
Expected: All tests PASS

**Step 2: Add `_parse_review()` to `LLMProvider` in `llm/base.py`**

Add to `llm/base.py` — import `json` and `logging` at top, add method to `LLMProvider` class:

```python
import json
import logging

logger = logging.getLogger(__name__)
```

Add to `LLMProvider` class (after the abstract methods):

```python
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

**Step 3: Remove `_parse_review()` from all three providers**

In `llm/ollama.py`: remove lines 59-81 (the `_parse_review` method), remove `import json`
In `llm/openai.py`: remove lines 53-75 (the `_parse_review` method), remove `import json`
In `llm/enterprise.py`: remove lines 76-98 (the `_parse_review` method), remove `import json`

Each provider's `review_code()` method calls `self._parse_review(content)` which now resolves to the base class.

**Step 4: Verify all existing tests still pass**

Run: `pytest tests/test_llm/ -v`
Expected: All tests PASS (identical behavior, just code location changed)

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/base.py src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py
git commit -m "refactor: extract _parse_review() to LLMProvider base class"
```

---

### Task 3: Consolidate prompts (response schema + commit improve)

**Files:**
- Modify: `src/ai_code_review/prompts.py` — add `REVIEW_RESPONSE_SCHEMA`
- Modify: `src/ai_code_review/llm/ollama.py` — remove `_REVIEW_RESPONSE_SCHEMA`, use shared prompt for `improve_commit_msg`
- Modify: `src/ai_code_review/llm/openai.py` — same
- Modify: `src/ai_code_review/llm/enterprise.py` — same

**Step 1: Verify all existing tests pass before refactoring**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 2: Add `REVIEW_RESPONSE_SCHEMA` to `prompts.py`**

Add after `_REVIEW_PROMPT`:

```python
REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""
```

**Step 3: Update all three providers**

For each provider (`ollama.py`, `openai.py`, `enterprise.py`):

1. Remove the module-level `_REVIEW_RESPONSE_SCHEMA` constant
2. Add import: `from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt`
   (Note: `ollama.py` and `enterprise.py` use `from .base import ...`; the prompts import uses `..prompts`)
3. In `review_code()`, change `_REVIEW_RESPONSE_SCHEMA` reference to `REVIEW_RESPONSE_SCHEMA`
4. Replace `improve_commit_msg()` body with:

```python
    def improve_commit_msg(self, message: str, diff: str) -> str:
        prompt = get_commit_improve_prompt(message, diff)
        return self._chat(prompt).strip()
```

**Step 4: Verify all existing tests still pass**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/prompts.py src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py
git commit -m "refactor: consolidate REVIEW_RESPONSE_SCHEMA and commit improve prompt into prompts.py"
```

---

### Task 4: Replace `sys.exit()` with exceptions in `_build_provider()`

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write tests for the new exception-based behavior**

Add to `tests/test_cli.py`:

```python
from ai_code_review.exceptions import ProviderNotConfiguredError

class TestBuildProvider:
    @patch("ai_code_review.cli.Config")
    def test_raises_when_no_provider(self, mock_config_cls):
        from ai_code_review.cli import _build_provider
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = None
        mock_config_cls.return_value = mock_config
        with pytest.raises(ProviderNotConfiguredError):
            _build_provider(mock_config, None, None)

    @patch("ai_code_review.cli.Config")
    def test_raises_for_unknown_provider(self, mock_config_cls):
        from ai_code_review.cli import _build_provider
        mock_config = MagicMock()
        mock_config.resolve_provider.return_value = "nonexistent"
        mock_config_cls.return_value = mock_config
        with pytest.raises(ProviderNotConfiguredError):
            _build_provider(mock_config, None, None)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestBuildProvider -v`
Expected: FAIL (currently raises `SystemExit`, not `ProviderNotConfiguredError`)

**Step 3: Update `_build_provider()` in `cli.py`**

Import the exception:
```python
from .exceptions import ProviderNotConfiguredError, ProviderError
```

Change `_build_provider()` — replace all `sys.exit(1)` with `raise`:

```python
def _build_provider(config: Config, cli_provider: str | None, cli_model: str | None) -> LLMProvider:
    provider_name = config.resolve_provider(cli_provider)
    if not provider_name:
        raise ProviderNotConfiguredError(
            "No provider configured. Available providers: ollama, openai, enterprise.\n"
            "Run: ai-review config set provider default <name>"
        )

    if provider_name == "ollama":
        base_url = config.get("ollama", "base_url") or "http://localhost:11434"
        model = cli_model or config.get("ollama", "model") or "codellama"
        return OllamaProvider(base_url=base_url, model=model)

    elif provider_name == "openai":
        token = config.resolve_token("openai")
        if not token:
            env_var = config.get("openai", "api_key_env") or "OPENAI_API_KEY"
            raise ProviderNotConfiguredError(
                f"OpenAI API key not found. Set env var {env_var} "
                f"(or configure: ai-review config set openai api_key_env <VAR_NAME>)"
            )
        model = cli_model or config.get("openai", "model") or "gpt-4o"
        base_url = config.get("openai", "base_url")
        return OpenAIProvider(api_key=token, model=model, base_url=base_url)

    elif provider_name == "enterprise":
        token = config.resolve_token("enterprise") or ""
        base_url = config.get("enterprise", "base_url")
        if not base_url:
            raise ProviderNotConfiguredError(
                "Enterprise base_url not configured.\n"
                "Run: ai-review config set enterprise base_url <URL>"
            )
        api_path = config.get("enterprise", "api_path") or "/v1/chat/completions"
        model = cli_model or config.get("enterprise", "model") or "default"
        auth_type = config.get("enterprise", "auth_type") or "bearer"
        return EnterpriseProvider(
            base_url=base_url, api_path=api_path, model=model,
            auth_type=auth_type, auth_token=token,
        )

    raise ProviderNotConfiguredError(f"Unknown provider: {provider_name}")
```

Update `_review()` to catch the exception at CLI boundary:

```python
def _review(ctx: click.Context) -> None:
    # ... (existing code up to custom_rules) ...

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError as e:
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    # ... rest unchanged ...
```

Update `check_commit()` to catch `ProviderNotConfiguredError` instead of `SystemExit`:

```python
    try:
        config = Config()
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError:
        # No provider configured — skip AI improvement silently
        return
```

**Step 4: Run all tests to verify**

Run: `pytest tests/ -v`
Expected: All tests PASS (existing tests that relied on `SystemExit` still work because CLI boundary catches and calls `sys.exit`)

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "refactor: replace sys.exit() with ProviderNotConfiguredError in _build_provider()"
```

---

### Task 5: Narrow bare exception handlers

**Files:**
- Modify: `src/ai_code_review/cli.py`

**Step 1: Verify all tests pass**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 2: Replace bare `except Exception` in `cli.py`**

In `hook_status()` (two occurrences, around lines 356 and 378):
```python
# Before:
except Exception:
    console.print("  [dim]not configured[/]")

# After:
except (subprocess.CalledProcessError, OSError):
    console.print("  [dim]not configured[/]")
```

In `hook_enable()` (around line 415):
```python
# Before:
except Exception:
    console.print("[bold red]Not in a git repository.[/]")

# After:
except (subprocess.CalledProcessError, OSError, GitError):
    console.print("[bold red]Not in a git repository.[/]")
```

In `hook_disable()` (around line 434):
```python
# Before:
except Exception:
    console.print("[bold red]Not in a git repository.[/]")

# After:
except (subprocess.CalledProcessError, OSError, GitError):
    console.print("[bold red]Not in a git repository.[/]")
```

In `_get_repo_hooks_dir()` (around line 566):
```python
# Before:
except Exception:
    console.print("[bold red]Not in a git repository.[/]")

# After:
except (subprocess.CalledProcessError, OSError, GitError):
    console.print("[bold red]Not in a git repository.[/]")
```

Ensure `subprocess` is imported at top of file (it's currently imported inside functions — add at top-level), and `GitError` is already imported.

**Step 3: Verify all tests still pass**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/ai_code_review/cli.py
git commit -m "refactor: narrow bare except Exception to specific exception types"
```

---

### Task 6: `health_check()` returns `tuple[bool, str]`

**Files:**
- Modify: `src/ai_code_review/llm/base.py` — change abstract signature
- Modify: `src/ai_code_review/llm/ollama.py`
- Modify: `src/ai_code_review/llm/openai.py`
- Modify: `src/ai_code_review/llm/enterprise.py`
- Modify: `src/ai_code_review/reviewer.py`
- Modify: `tests/test_llm/test_ollama.py`
- Modify: `tests/test_llm/test_openai.py`
- Modify: `tests/test_llm/test_enterprise.py`
- Modify: `tests/test_reviewer.py`

**Step 1: Update tests to expect tuple return**

In `tests/test_llm/test_ollama.py`, update `TestOllamaHealthCheck`:
```python
class TestOllamaHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(200, json={"models": []})
        )
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("refused"))
        ok, msg = provider.health_check()
        assert ok is False
        assert msg  # has a reason

    @respx.mock
    def test_unhealthy_http_error(self, provider):
        respx.get("http://localhost:11434/api/tags").mock(
            return_value=httpx.Response(500)
        )
        ok, msg = provider.health_check()
        assert ok is False
        assert "500" in msg
```

In `tests/test_llm/test_openai.py`, update `TestOpenAIHealthCheck`:
```python
class TestOpenAIHealthCheck:
    @patch("ai_code_review.llm.openai.OpenAI")
    def test_healthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.return_value = []
        provider._client = mock_cls.return_value
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @patch("ai_code_review.llm.openai.OpenAI")
    def test_unhealthy(self, mock_cls, provider):
        mock_cls.return_value.models.list.side_effect = Exception("connection refused")
        provider._client = mock_cls.return_value
        ok, msg = provider.health_check()
        assert ok is False
        assert "connection refused" in msg.lower()
```

In `tests/test_llm/test_enterprise.py`, update `TestEnterpriseHealthCheck`:
```python
class TestEnterpriseHealthCheck:
    @respx.mock
    def test_healthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        ok, msg = provider.health_check()
        assert ok is True
        assert "connected" in msg.lower()

    @respx.mock
    def test_unhealthy(self, provider):
        respx.get("https://llm.internal.company.com/v1/models").mock(
            side_effect=httpx.ConnectError("refused")
        )
        ok, msg = provider.health_check()
        assert ok is False
        assert msg
```

In `tests/test_reviewer.py`, update `TestHealthCheck`:
```python
class TestHealthCheck:
    def test_delegates_to_provider(self, reviewer, mock_provider):
        mock_provider.health_check.return_value = (True, "Connected")
        ok, msg = reviewer.check_provider_health()
        assert ok is True
        mock_provider.health_check.assert_called_once()
```

And update the `mock_provider` fixture:
```python
@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.review_code.return_value = ReviewResult(issues=[
        ReviewIssue(severity=Severity.WARNING, file="a.c", line=1, message="minor"),
    ])
    provider.improve_commit_msg.return_value = "[BSP-1] improved message"
    provider.health_check.return_value = (True, "Connected")
    return provider
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/ tests/test_reviewer.py -v`
Expected: FAIL (health_check still returns bool)

**Step 3: Update implementations**

In `llm/base.py`, change the abstract method signature:
```python
    @abstractmethod
    def health_check(self) -> tuple[bool, str]: ...
```

In `llm/ollama.py`:
```python
    def health_check(self) -> tuple[bool, str]:
        try:
            resp = self._client.get(f"{self._base_url}/api/tags")
            if resp.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, f"Connection refused: {self._base_url}"
        except httpx.TimeoutException:
            return False, f"Timeout connecting to {self._base_url}"
        except httpx.HTTPError as e:
            return False, str(e)
```

In `llm/openai.py`:
```python
    def health_check(self) -> tuple[bool, str]:
        try:
            self._client.models.list()
            return True, "Connected"
        except Exception as e:
            return False, str(e)
```

In `llm/enterprise.py`:
```python
    def health_check(self) -> tuple[bool, str]:
        try:
            resp = self._client.get(f"{self._base_url}/v1/models")
            if resp.status_code == 200:
                return True, "Connected"
            return False, f"HTTP {resp.status_code}"
        except httpx.ConnectError:
            return False, f"Connection refused: {self._base_url}"
        except httpx.TimeoutException:
            return False, f"Timeout connecting to {self._base_url}"
        except httpx.HTTPError as e:
            return False, str(e)
```

In `reviewer.py`:
```python
    def check_provider_health(self) -> tuple[bool, str]:
        return self._provider.health_check()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm/ tests/test_reviewer.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/base.py src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py src/ai_code_review/reviewer.py tests/test_llm/ tests/test_reviewer.py
git commit -m "feat: health_check() now returns (bool, str) with failure reason"
```

---

### Task 7: HTTP retry and configurable timeout

**Files:**
- Modify: `src/ai_code_review/llm/ollama.py`
- Modify: `src/ai_code_review/llm/openai.py`
- Modify: `src/ai_code_review/llm/enterprise.py`
- Modify: `src/ai_code_review/cli.py`
- Modify: `tests/test_llm/test_ollama.py`
- Modify: `tests/test_llm/test_enterprise.py`

**Step 1: Write tests for configurable timeout**

Add to `tests/test_llm/test_ollama.py`:
```python
class TestOllamaTimeout:
    def test_default_timeout(self):
        p = OllamaProvider(base_url="http://localhost:11434", model="codellama")
        assert p._client.timeout.connect == 120.0

    def test_custom_timeout(self):
        p = OllamaProvider(base_url="http://localhost:11434", model="codellama", timeout=30)
        assert p._client.timeout.connect == 30.0
```

Add to `tests/test_llm/test_enterprise.py`:
```python
class TestEnterpriseTimeout:
    def test_default_timeout(self):
        p = EnterpriseProvider(
            base_url="https://llm.example.com", api_path="/v1/chat/completions",
            model="model", auth_type="bearer", auth_token="tok",
        )
        assert p._client.timeout.connect == 120.0

    def test_custom_timeout(self):
        p = EnterpriseProvider(
            base_url="https://llm.example.com", api_path="/v1/chat/completions",
            model="model", auth_type="bearer", auth_token="tok", timeout=60,
        )
        assert p._client.timeout.connect == 60.0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_ollama.py::TestOllamaTimeout tests/test_llm/test_enterprise.py::TestEnterpriseTimeout -v`
Expected: FAIL (constructors don't accept `timeout` param)

**Step 3: Update provider constructors**

In `llm/ollama.py`:
```python
_DEFAULT_TIMEOUT = 120.0

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        transport = httpx.HTTPTransport(retries=3)
        self._client = httpx.Client(timeout=timeout, transport=transport)
```

In `llm/enterprise.py`:
```python
_DEFAULT_TIMEOUT = 120.0

class EnterpriseProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_path: str,
        model: str,
        auth_type: str = "bearer",
        auth_token: str = "",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_path = api_path
        self._model = model
        self._headers = self._build_auth_headers(auth_type, auth_token)
        transport = httpx.HTTPTransport(retries=3)
        self._client = httpx.Client(timeout=timeout, headers=self._headers, transport=transport)
```

In `llm/openai.py`, add `timeout` parameter:
```python
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None, timeout: float = 120.0) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=3)
```

Update `_build_provider()` in `cli.py` to pass timeout from config:

For each provider block, read timeout:
```python
    if provider_name == "ollama":
        base_url = config.get("ollama", "base_url") or "http://localhost:11434"
        model = cli_model or config.get("ollama", "model") or "codellama"
        timeout = float(config.get("ollama", "timeout") or 120)
        return OllamaProvider(base_url=base_url, model=model, timeout=timeout)
```

Same pattern for `openai` and `enterprise` blocks.

**Step 4: Run all tests to verify**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py src/ai_code_review/cli.py tests/test_llm/
git commit -m "feat: add HTTP retry (3 attempts) and configurable timeout per provider"
```

---

### Task 8: Diff size limit

**Files:**
- Modify: `src/ai_code_review/config.py` — add default constant
- Modify: `src/ai_code_review/cli.py` — add truncation logic
- Test: `tests/test_cli.py` — add truncation tests

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        # Verify the diff passed to provider is truncated
        diff_arg = mock_provider.review_code.call_args[0][0]
        assert diff_arg.count("\n") <= 2001  # 2000 lines + truncation notice
        assert "truncated" in diff_arg.lower()

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    @patch("ai_code_review.cli.Config")
    def test_small_diff_not_truncated(self, mock_config_cls, mock_diff, mock_build, runner):
        small_diff = "\n".join(f"line {i}" for i in range(100))
        mock_diff.return_value = small_diff
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        result = runner.invoke(main, [])
        diff_arg = mock_provider.review_code.call_args[0][0]
        assert "truncated" not in diff_arg.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestDiffTruncation -v`
Expected: FAIL

**Step 3: Implement truncation logic**

In `config.py`, add:
```python
DEFAULT_MAX_DIFF_LINES = 2000
```

In `cli.py`, update `_review()` — after getting the diff and before calling provider, add truncation:

```python
from .config import DEFAULT_INCLUDE_EXTENSIONS, DEFAULT_MAX_DIFF_LINES, Config
```

In `_review()`, after `if not diff: ... return`:

```python
    # Truncate large diffs
    max_lines_raw = config.get("review", "max_diff_lines")
    max_lines = int(max_lines_raw) if max_lines_raw else DEFAULT_MAX_DIFF_LINES
    lines = diff.split("\n")
    if len(lines) > max_lines:
        console.print(f"[yellow]Warning: diff truncated to {max_lines} lines (original: {len(lines)} lines)[/]")
        diff = "\n".join(lines[:max_lines]) + f"\n... (truncated: showing first {max_lines} of {len(lines)} lines)"
```

**Step 4: Run tests to verify**

Run: `pytest tests/test_cli.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/config.py src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add diff size limit (review.max_diff_lines, default 2000)"
```

---

### Task 9: `ai-review health-check` command

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
        mock_config.resolve_provider.return_value = None
        mock_config_cls.return_value = mock_config

        result = runner.invoke(main, ["health-check"])
        assert result.exit_code == 1
        assert "no provider" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestHealthCheckCommand -v`
Expected: FAIL (command doesn't exist yet)

**Step 3: Implement the command**

Add to `cli.py`, after `check_commit()`:

```python
@main.command("health-check")
@click.pass_context
def health_check_cmd(ctx: click.Context) -> None:
    """Check LLM provider connectivity."""
    config = Config()
    cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
    cli_model = ctx.obj.get("cli_model") if ctx.obj else None

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError as e:
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    provider_name = config.resolve_provider(cli_provider)
    model = cli_model or config.get(provider_name, "model") or "default"
    console.print(f"Provider: {rich_escape(provider_name)} ({rich_escape(model)})")

    ok, msg = provider.health_check()
    if ok:
        console.print(f"[green]Status: OK ({rich_escape(msg)})[/]")
    else:
        console.print(f"[bold red]Status: FAILED — {rich_escape(msg)}[/]")
        sys.exit(1)
```

**Step 4: Run tests to verify**

Run: `pytest tests/test_cli.py::TestHealthCheckCommand -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add 'ai-review health-check' command to validate LLM connectivity"
```

---

### Task 10: `ai-review config show` command

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestConfigShowCommand -v`
Expected: FAIL (command doesn't exist)

**Step 3: Implement the command**

Add to `cli.py`, in the config group:

```python
@config_group.command("show")
@click.argument("section", required=False)
def config_show(section: str | None) -> None:
    """Show current configuration."""
    config = Config()
    data = config._data

    if not data:
        console.print("[dim]No configuration set.[/]")
        return

    if section:
        if section not in data:
            console.print(f"[dim]Section '{rich_escape(section)}' not found.[/]")
            return
        _print_config_section(section, data[section])
    else:
        for sect_name, sect_data in data.items():
            _print_config_section(sect_name, sect_data)
            console.print()


def _print_config_section(name: str, data: dict) -> None:
    console.print(f"[bold][{rich_escape(name)}][/]")
    for key, value in data.items():
        console.print(f"  {rich_escape(key)} = {rich_escape(str(value))}")
```

**Step 4: Run tests to verify**

Run: `pytest tests/test_cli.py::TestConfigShowCommand -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add 'ai-review config show [section]' command"
```

---

### Task 11: `--verbose` / `-v` global flag

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
import logging

class TestVerboseFlag:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_verbose_enables_debug_logging(self, mock_diff, mock_build, runner):
        mock_diff.return_value = ""
        result = runner.invoke(main, ["-v"])
        # Check that ai_code_review logger is set to DEBUG
        logger = logging.getLogger("ai_code_review")
        assert logger.level == logging.DEBUG

    def test_no_verbose_default_logging(self, runner):
        # Reset logger level before test
        logger = logging.getLogger("ai_code_review")
        logger.setLevel(logging.WARNING)
        result = runner.invoke(main, [], input="")
        # Without -v, logger should remain at WARNING (or not be set to DEBUG)
        assert logger.level != logging.DEBUG
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::TestVerboseFlag -v`
Expected: FAIL (no `-v` flag)

**Step 3: Implement the flag**

In `cli.py`, update `main()`:

```python
@click.group(invoke_without_command=True)
@click.option("--provider", "cli_provider", default=None, help="LLM provider (ollama/openai/enterprise)")
@click.option("--model", "cli_model", default=None, help="Model name")
@click.option("--format", "output_format", default="terminal", type=click.Choice(["terminal", "markdown", "json"]))
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, cli_provider: str | None, cli_model: str | None, output_format: str, verbose: bool) -> None:
    """AI-powered code review for Android BSP teams."""
    ctx.ensure_object(dict)
    ctx.obj["cli_provider"] = cli_provider
    ctx.obj["cli_model"] = cli_model
    ctx.obj["output_format"] = output_format

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="[DEBUG] %(message)s")
        logging.getLogger("ai_code_review").setLevel(logging.DEBUG)

    if ctx.invoked_subcommand is None:
        _review(ctx)
```

**Step 4: Run tests to verify**

Run: `pytest tests/test_cli.py::TestVerboseFlag -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add --verbose / -v flag for debug logging"
```

---

### Task 12: Edge case tests for `_parse_review()`

These tests exercise the shared `_parse_review()` now in the base class. Use OllamaProvider as the concrete test target (simplest setup).

**Files:**
- Modify: `tests/test_llm/test_ollama.py`

**Step 1: Write edge case tests**

Add to `tests/test_llm/test_ollama.py`:

```python
class TestParseReviewEdgeCases:
    @respx.mock
    def test_markdown_fence_json(self, provider):
        """LLM wraps response in ```json ... ``` fences."""
        content = '```json\n[{"severity":"warning","file":"a.c","line":1,"message":"test"}]\n```'
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.WARNING

    @respx.mock
    def test_markdown_fence_no_lang(self, provider):
        """LLM wraps response in ``` ... ``` without language tag."""
        content = '```\n[{"severity":"info","file":"b.c","line":5,"message":"note"}]\n```'
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1
        assert result.issues[0].severity == Severity.INFO

    @respx.mock
    def test_malformed_json(self, provider):
        """LLM returns invalid JSON — should return empty result, not crash."""
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": "{not valid json}"}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0

    @respx.mock
    def test_empty_response(self, provider):
        """LLM returns empty string."""
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": ""}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0

    @respx.mock
    def test_missing_fields_skipped(self, provider):
        """Items missing required fields are skipped."""
        content = json.dumps([
            {"severity": "warning", "file": "a.c", "line": 1, "message": "ok"},
            {"severity": "warning"},  # missing file, line, message
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 1  # only the valid one

    @respx.mock
    def test_invalid_severity_skipped(self, provider):
        """Items with invalid severity value are skipped."""
        content = json.dumps([
            {"severity": "fatal", "file": "a.c", "line": 1, "message": "bad severity"},
        ])
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"role": "assistant", "content": content}
            })
        )
        result = provider.review_code("diff", "prompt")
        assert len(result.issues) == 0
```

**Step 2: Run tests**

Run: `pytest tests/test_llm/test_ollama.py::TestParseReviewEdgeCases -v`
Expected: All PASS (the _parse_review implementation already handles these cases; we're adding coverage)

**Step 3: Commit**

```bash
git add tests/test_llm/test_ollama.py
git commit -m "test: add edge case tests for _parse_review (markdown fences, malformed JSON, missing fields)"
```

---

### Task 13: Final full test run and CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (should be ~125+ tests now)

**Step 2: Run with count**

Run: `pytest tests/ -v --tb=short | tail -5`
Expected: Shows total test count and `passed`

**Step 3: Update CLAUDE.md test count and new features**

Update these sections in `CLAUDE.md`:

- Test count: update `110 tests` to the actual new count
- Commands section: add `ai-review health-check` and `ai-review config show [section]`
- Key Patterns section: mention `--verbose` flag
- Architecture: mention `exceptions.py`

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with new commands, test count, and architecture changes"
```

---

## Task Dependency Order

```
Task 1 (exceptions) ──────────────────────────────────────┐
Task 2 (extract _parse_review) ─────┐                     │
Task 3 (consolidate prompts) ───────┼─ Task 4 (exceptions in CLI) ─── Task 5 (narrow handlers)
                                    │
Task 6 (health_check tuple) ────────┼─ Task 9 (health-check cmd)
                                    │
Task 7 (retry + timeout) ──────────┘
                                        Task 10 (config show)
Task 8 (diff limit) ──────────────────  Task 11 (verbose flag)
                                        Task 12 (edge case tests)
                                        Task 13 (final verification)
```

Tasks 1-3 can run in parallel. Tasks 8, 10, 11, 12 can run in parallel after Task 4.
