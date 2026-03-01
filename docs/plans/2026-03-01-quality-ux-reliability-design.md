# Quality, UX & Reliability Optimization Design

Date: 2026-03-01

## Goal

Improve ai-code-review across three dimensions without changing external behavior (except where adding new features):

1. **Code Quality / DRY** — eliminate duplication, improve error handling
2. **CLI UX** — new commands, better error messages, debug mode
3. **Reliability** — retry logic, configurable timeouts, diff limits, better tests

---

## Area 1: Code Quality / DRY

### 1.1 Extract `_parse_review()` to base class

**Problem**: Identical 23-line method in OllamaProvider, OpenAIProvider, EnterpriseProvider.

**Solution**: Move `_parse_review()` to `LLMProvider` in `llm/base.py`. All three providers inherit it. Remove from each provider file.

**Files changed**: `llm/base.py`, `llm/ollama.py`, `llm/openai.py`, `llm/enterprise.py`

### 1.2 Consolidate `_REVIEW_RESPONSE_SCHEMA` and commit improve prompt

**Problem**:
- `_REVIEW_RESPONSE_SCHEMA` defined identically in all 3 provider files
- `improve_commit_msg()` has identical inline prompt in all 3 providers, while `prompts.py` already has `_COMMIT_IMPROVE_PROMPT`

**Solution**:
- Move `_REVIEW_RESPONSE_SCHEMA` to `prompts.py` as `REVIEW_RESPONSE_SCHEMA`
- Make all providers use `get_commit_improve_prompt()` from `prompts.py`
- Each provider's `improve_commit_msg()` just calls `self._chat(prompt).strip()` with the shared prompt

**Files changed**: `prompts.py`, `llm/ollama.py`, `llm/openai.py`, `llm/enterprise.py`

### 1.3 Custom exception hierarchy

**Problem**:
- `_build_provider()` calls `sys.exit(1)` for errors
- `check_commit()` catches `SystemExit` to handle "no provider" case — fragile
- Various bare `except Exception` blocks

**Solution**: Create `exceptions.py`:

```python
class AIReviewError(Exception):
    """Base exception for ai-code-review."""

class ProviderNotConfiguredError(AIReviewError):
    """No LLM provider configured."""

class ProviderError(AIReviewError):
    """LLM provider failed (connection, auth, response)."""
```

- `_build_provider()` raises `ProviderNotConfiguredError` instead of `sys.exit(1)`
- CLI commands catch specific exceptions, call `sys.exit(1)` only at the CLI boundary
- `check_commit()` catches `ProviderNotConfiguredError` instead of `SystemExit`

**Files changed**: new `exceptions.py`, `cli.py`

### 1.4 Narrow bare exception handlers

**Problem**: `except Exception` in `hook_status()`, `hook_enable()`, `_get_repo_hooks_dir()` swallows everything including `KeyboardInterrupt`.

**Solution**: Replace with specific types:
- `except (subprocess.CalledProcessError, OSError)` for git/subprocess operations
- `except GitError` where appropriate

**Files changed**: `cli.py`

---

## Area 2: CLI UX

### 2.1 `ai-review health-check` command

**Purpose**: Validate LLM provider connectivity before first use.

**Behavior**:
```
$ ai-review health-check
Provider: openai (gpt-4o)
Status: OK (connected)

$ ai-review health-check
Provider: ollama (codellama)
Status: FAILED — Connection refused: http://localhost:11434
```

**Implementation**:
- New `health_check` command in `cli.py`
- Uses provider's `health_check()` method (updated to return `tuple[bool, str]`)
- Shows provider name, model, and connection status with reason

**Files changed**: `cli.py`, `llm/base.py`, `llm/ollama.py`, `llm/openai.py`, `llm/enterprise.py`

### 2.2 `ai-review config show [section]` command

**Purpose**: Display all current config values at a glance.

**Behavior**:
```
$ ai-review config show
[provider]
  default = openai

[openai]
  api_key_env = OPENAI_API_KEY
  model = gpt-4o

[review]
  include_extensions = c,cpp,h,hpp,java
  custom_rules = Check for integer overflow

$ ai-review config show openai
[openai]
  api_key_env = OPENAI_API_KEY
  model = gpt-4o
```

**Implementation**:
- New `config show` subcommand accepting optional `section` argument
- Reads from Config._data and formats output
- No token masking needed (config only stores env var names, not actual tokens)

**Files changed**: `cli.py`

### 2.3 Improved error messages

**Current → Improved**:
- `"No provider configured. Run: ai-review config set provider default <name>"` → `"No provider configured. Available providers: ollama, openai, enterprise. Run: ai-review config set provider default <name>"`
- `"OpenAI API key not found. Set the env var specified in config."` → `"OpenAI API key not found. Set env var OPENAI_API_KEY (or configure a different env var name with: ai-review config set openai api_key_env <VAR_NAME>)"`

**Files changed**: `cli.py` (in `_build_provider()`)

### 2.4 `--verbose` / `-v` global flag

**Purpose**: Enable debug logging for troubleshooting.

**Behavior**:
```
$ ai-review -v
[DEBUG] Config loaded from ~/.config/ai-code-review/config.toml
[DEBUG] Provider: openai (gpt-4o)
[DEBUG] Staged diff: 45 lines (2 files)
[DEBUG] Sending review request...
[DEBUG] Response received in 3.2s
...normal output...
```

**Implementation**:
- Add `--verbose` / `-v` flag to `main` group
- When enabled, set logging level to DEBUG for `ai_code_review` logger
- All providers already use `logger.debug/warning` — just need to configure the handler

**Files changed**: `cli.py`

---

## Area 3: Reliability

### 3.1 HTTP retry with exponential backoff

**Problem**: Network glitches cause immediate failure with no recovery.

**Solution**:
- For httpx-based providers (Ollama, Enterprise): use `httpx.Client(transport=httpx.HTTPTransport(retries=3))`
- OpenAI SDK: already has built-in retry (`max_retries` parameter, default 2)
- Retry on: connection errors, 429 (rate limit), 500/502/503/504 (server errors)

**Files changed**: `llm/ollama.py`, `llm/enterprise.py`

### 3.2 Configurable timeout

**Problem**: Hardcoded `timeout=120.0` — too long for some, too short for large models.

**Solution**:
- New config option: `[ollama] timeout = 120`, `[openai] timeout = 60`, `[enterprise] timeout = 120`
- Provider constructors accept `timeout` parameter
- `_build_provider()` reads timeout from config and passes it

**Default**: 120 seconds (unchanged behavior).

**Files changed**: `llm/ollama.py`, `llm/openai.py`, `llm/enterprise.py`, `cli.py`

### 3.3 Diff size limit

**Problem**: Very large diffs can exceed LLM context window or cause timeouts.

**Solution**:
- New config option: `review.max_diff_lines = 2000` (default)
- When diff exceeds limit, truncate and append `\n... (truncated: showing first N of M lines)`
- Print warning to user: `"Warning: diff truncated to 2000 lines (original: 5432 lines)"`

**Files changed**: `cli.py`, `config.py` (new default constant)

### 3.4 `health_check()` returns reason

**Problem**: `health_check() -> bool` — no way to know why it failed.

**Solution**: Change signature to `health_check() -> tuple[bool, str]`:
```python
def health_check(self) -> tuple[bool, str]:
    try:
        resp = self._client.get(...)
        if resp.status_code == 200:
            return True, "Connected"
        return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError as e:
        return False, f"Connection refused: {self._base_url}"
    except httpx.TimeoutException:
        return False, f"Timeout after {self._timeout}s"
```

**Files changed**: `llm/base.py`, `llm/ollama.py`, `llm/openai.py`, `llm/enterprise.py`

### 3.5 Additional test coverage

New tests to add:

- **Timeout simulation**: respx mock with timeout, verify graceful error
- **Malformed JSON responses**: various broken formats (`{not json}`, empty string, nested markdown fences)
- **Markdown fence variants**: ` ```json\n[...]\n``` `, ` ```\n[...]\n``` `
- **Diff truncation**: verify truncation at configured limit, warning message
- **Health check with reason**: verify error message on various failure modes
- **Retry behavior**: verify retry on 429/5xx for httpx providers
- **Config show**: all output formatting cases
- **Verbose mode**: verify debug logging is activated

**Files changed**: new tests across `tests/test_*.py` files

---

## Files Summary

| File | Action | Area |
|------|--------|------|
| `src/ai_code_review/exceptions.py` | New | Quality |
| `src/ai_code_review/llm/base.py` | Modify | Quality, Reliability |
| `src/ai_code_review/llm/ollama.py` | Modify | Quality, Reliability |
| `src/ai_code_review/llm/openai.py` | Modify | Quality, Reliability |
| `src/ai_code_review/llm/enterprise.py` | Modify | Quality, Reliability |
| `src/ai_code_review/prompts.py` | Modify | Quality |
| `src/ai_code_review/cli.py` | Modify | Quality, UX, Reliability |
| `src/ai_code_review/config.py` | Modify | Reliability |
| `tests/test_providers.py` | Modify | Reliability |
| `tests/test_cli.py` | Modify | UX |

## Non-goals

- No new LLM providers
- No CI/CD pipeline integration
- No review history / persistence
- No file exclusion patterns (future work)
- No severity customization (future work)
