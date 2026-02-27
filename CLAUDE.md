# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered code review CLI (`ai-review`) for Android BSP engineering teams. Catches serious defects before commit, enforces `[PROJECT-NUMBER] description` commit message format, and provides AI-powered commit message grammar/clarity improvement.

Designed for teams that push directly to main across hundreds of internal GitLab repos. Supports local Ollama, enterprise internal LLM, and external OpenAI as backends.

## Commands

```bash
# Setup (virtual env at .venv/)
pip install -e ".[dev]"

# Tests (81 tests, pytest + respx + pytest-mock)
pytest                            # run all
pytest tests/test_cli.py -v       # single file
pytest -k "test_healthy" -v       # pattern match

# CLI usage
ai-review                         # review staged diff (default: terminal output)
ai-review --format json           # JSON output
ai-review --format markdown       # Markdown output
ai-review --provider ollama --model llama3.1  # override provider/model
ai-review check-commit <file>     # validate + AI-improve commit message
ai-review config set <section> <key> <value>
ai-review config get <section> <key>
ai-review hook install pre-commit  # install git hook (non-pre-commit-framework)
ai-review hook install commit-msg
ai-review hook uninstall pre-commit
ai-review hook status
```

## Architecture

```
src/ai_code_review/
  cli.py           # click CLI: main group, _review(), check_commit(), config, hook subcommands
  config.py        # Config class — TOML read/write at ~/.config/ai-code-review/config.toml
  commit_check.py  # check_commit_message() — regex [A-Z]+-\d+ validation
  git.py           # get_staged_diff(), get_unstaged_diff(), get_commit_diff(), GitError
  reviewer.py      # Reviewer — orchestrates LLM provider calls with prompts
  prompts.py       # Android BSP review prompt + commit message improvement prompt
  formatters.py    # format_terminal() / format_markdown() / format_json()
  llm/
    base.py        # LLMProvider ABC, Severity enum, ReviewIssue, ReviewResult
    ollama.py      # OllamaProvider — Ollama REST API (/api/chat), httpx
    openai.py      # OpenAIProvider — openai SDK
    enterprise.py  # EnterpriseProvider — httpx, configurable base_url/api_path/auth
```

## Key Data Flow

```
CLI (cli.py)
  → get_staged_diff() (git.py)
  → _build_provider() selects OllamaProvider / OpenAIProvider / EnterpriseProvider
  → Reviewer.review_diff() → provider.review_code(diff, prompt) → ReviewResult
  → format_terminal/markdown/json(result) → output
  → exit(1) if result.is_blocked (critical/error severity)

check-commit flow:
  → check_commit_message() regex validation (commit_check.py)
  → if valid + file provided + provider configured + diff exists:
    → Reviewer.improve_commit_message() → show suggestion
    → interactive [A]ccept / [E]dit / [S]kip → update file if accepted
```

## Key Patterns

- **Provider pattern**: All LLM backends implement `LLMProvider` ABC (`review_code()`, `improve_commit_msg()`, `health_check()`). New provider = one new file in `llm/`.
- **JSON response parsing**: All providers expect LLM to return `[{"severity", "file", "line", "message"}]`. `_parse_review()` handles markdown fences and malformed items gracefully.
- **Config resolution order**: `--provider` CLI flag > `config.toml [provider].default` > auto-detect. API tokens always read from env vars (never in config files).
- **Severity blocking**: `Severity.blocks` property — `critical`/`error` return True (block commit), `warning`/`info` return False.
- **Prompt templates** in `prompts.py`: review prompt focuses on memory leaks, null pointer, race conditions, hardcoded secrets, buffer overflow. Explicitly excludes style/naming/refactoring suggestions.

## Testing Conventions

- `respx` mocks HTTP for Ollama and Enterprise providers (httpx-based)
- `unittest.mock` patches OpenAI SDK client
- `click.testing.CliRunner` for CLI integration tests
- `tmp_path` + real `git init` for git.py and hook tests
- No real LLM API calls in any test

## pre-commit Framework Integration

`.pre-commit-hooks.yaml` at project root provides two hooks:
- `ai-review-commit-msg` (commit-msg stage) — format check + AI improvement
- `ai-review-code` (pre-commit stage) — AI code review

Consumer repos add to `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: <this-repo-url>
    rev: v0.1.0
    hooks:
      - id: ai-review-commit-msg
      - id: ai-review-code
        args: ["--provider", "ollama"]
```
