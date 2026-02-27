# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered code review CLI (`ai-review`) for Android BSP engineering teams. Python 3.10+, installed via pip, uses click for CLI, rich for terminal output.

## Commands

```bash
# Setup
pip install -e ".[dev]"          # install with dev dependencies (uses .venv/)

# Tests
pytest                           # run all tests
pytest tests/test_config.py -v   # run a single test file
pytest -k "test_healthy" -v      # run tests matching a pattern

# Run the CLI
ai-review                        # review staged diff
ai-review check-commit           # check commit message format
ai-review config set <s> <k> <v> # set config value
ai-review hook status             # show installed hooks
```

## Architecture

```
src/ai_code_review/
  cli.py           # click CLI entry point — main(), _build_provider(), subcommands
  config.py        # Config class — reads/writes ~/.config/ai-code-review/config.toml
  commit_check.py  # check_commit_message() — regex validation for [PROJECT-NUMBER] format
  git.py           # get_staged_diff(), get_unstaged_diff(), get_commit_diff()
  reviewer.py      # Reviewer — orchestrates LLM calls using prompts.py
  prompts.py       # Android BSP-focused review prompt + commit message improvement prompt
  formatters.py    # format_terminal(), format_markdown(), format_json()
  llm/
    base.py        # LLMProvider ABC, Severity enum, ReviewIssue, ReviewResult
    ollama.py      # OllamaProvider — Ollama REST API (/api/chat)
    openai.py      # OpenAIProvider — OpenAI SDK
    enterprise.py  # EnterpriseProvider — configurable base URL + auth, OpenAI-compatible API
```

## Key Patterns

- **Provider pattern**: All LLM backends implement `LLMProvider` ABC with `review_code()`, `improve_commit_msg()`, `health_check()`. Adding a new provider = one new file in `llm/`.
- **Response parsing**: All providers parse LLM output as JSON arrays of `{"severity", "file", "line", "message"}`. The `_parse_review()` method handles markdown fences and malformed responses gracefully.
- **Config resolution**: CLI flags > config.toml defaults > auto-detect. Tokens always from env vars.
- **Severity blocking**: `critical`/`error` block commits; `warning`/`info` don't. Controlled by `Severity.blocks` property.
- **Tests use mocks**: LLM providers are tested with `respx` (for httpx-based providers) and `unittest.mock` (for OpenAI SDK). No real API calls in tests.

## pre-commit Integration

`.pre-commit-hooks.yaml` at project root defines two hooks: `ai-review-commit-msg` (commit-msg stage) and `ai-review-code` (pre-commit stage). Consumer repos reference this via `.pre-commit-config.yaml`.
