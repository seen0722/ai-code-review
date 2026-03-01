# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered code review CLI (`ai-review`) for Android BSP engineering teams. Catches serious defects before commit, enforces `[PROJECT-NUMBER] description` commit message format, and provides AI-powered commit message grammar/clarity improvement.

Designed for teams that push directly to main across hundreds of internal GitLab repos. Supports local Ollama, enterprise internal LLM, and external OpenAI as backends.

## Commands

```bash
# Setup (clone repo, then install in dev mode)
git clone https://github.com/seen0722/ai-code-review.git && cd ai-code-review
pip install -e ".[dev]"

# Tests (139 tests, pytest + respx + pytest-mock)
pytest                            # run all
pytest tests/test_cli.py -v       # single file
pytest -k "test_healthy" -v       # pattern match

# CLI usage
ai-review                         # review staged diff (default: terminal output)
ai-review -v                      # review with debug logging
ai-review --format json           # JSON output
ai-review --format markdown       # Markdown output
ai-review --provider ollama --model llama3.1  # override provider/model
ai-review health-check            # validate LLM provider connectivity
ai-review check-commit <file>     # validate + AI-improve commit message
ai-review check-commit --auto-accept <file>   # auto-accept AI suggestion (non-interactive)
ai-review config set <section> <key> <value>
ai-review config get <section> <key>
ai-review config show [section]   # display current configuration

# Hook management
ai-review hook install --template  # template hooks via init.templateDir (recommended)
ai-review hook uninstall --template # remove template hooks
ai-review hook install pre-commit  # per-repo hook
ai-review hook install commit-msg  # per-repo hook
ai-review hook uninstall pre-commit
ai-review hook uninstall commit-msg
ai-review hook enable              # enable ai-review for current repo (git config --local)
ai-review hook disable             # disable ai-review for current repo
ai-review hook status              # show template + per-repo hook status
```

## Architecture

```
src/ai_code_review/
  cli.py           # click CLI: main group, _review(), check_commit(), health_check_cmd(), config, hook subcommands
  config.py        # Config class — TOML read/write at ~/.config/ai-code-review/config.toml
  commit_check.py  # check_commit_message() — regex [A-Z]+-\d+ validation
  exceptions.py    # AIReviewError, ProviderNotConfiguredError, ProviderError
  git.py           # get_staged_diff(), get_unstaged_diff(), get_commit_diff(), GitError
  reviewer.py      # Reviewer — orchestrates LLM provider calls with prompts
  prompts.py       # Android BSP review prompt + commit message improvement prompt + REVIEW_RESPONSE_SCHEMA
  formatters.py    # format_terminal() / format_markdown() / format_json()
  llm/
    base.py        # LLMProvider ABC (with shared _parse_review()), Severity enum, ReviewIssue, ReviewResult
    ollama.py      # OllamaProvider — Ollama REST API (/api/chat), httpx, retry + configurable timeout
    openai.py      # OpenAIProvider — openai SDK, retry + configurable timeout
    enterprise.py  # EnterpriseProvider — httpx, configurable base_url/api_path/auth, retry + configurable timeout
```

## Key Data Flow

```
CLI (cli.py)
  → get_staged_diff() (git.py)
  → _build_provider() selects OllamaProvider / OpenAIProvider / EnterpriseProvider
  → config.get("review", "custom_rules") → optional custom rules
  → Reviewer.review_diff(diff, custom_rules) → get_review_prompt(custom_rules) → provider.review_code(diff, prompt) → ReviewResult
  → format_terminal/markdown/json(result) → output
  → exit(1) if result.is_blocked (critical/error severity)

check-commit flow:
  → check_commit_message() regex validation (commit_check.py)
  → if valid + file provided + provider configured + diff exists:
    → Reviewer.improve_commit_message() → show suggestion
    → --auto-accept or AI_REVIEW_AUTO_ACCEPT=1: auto-accept
    → interactive [A]ccept / [E]dit / [S]kip → update file if accepted
```

## Hook Deployment

### Template hooks (recommended)
- `ai-review hook install --template` creates scripts at `~/.config/ai-code-review/template/hooks/`
- Sets `git config --global init.templateDir` → new clones auto-get hooks in `.git/hooks/`
- Existing repos need `git init` to pick up template hooks
- **Opt-in**: hooks only activate in repos with `git config --local ai-review.enabled true`
- Enable: `ai-review hook enable` / Disable: `ai-review hook disable`
- Hook scripts use absolute path to `ai-review` executable (resolved at install time)
- Uninstall: `ai-review hook uninstall --template`

### Per-repo hooks
- `ai-review hook install pre-commit` / `commit-msg` writes to `.git/hooks/`
- Only affects the current repository, no opt-in check

## Key Patterns

- **Provider pattern**: All LLM backends implement `LLMProvider` ABC (`review_code()`, `improve_commit_msg()`, `health_check()`). New provider = one new file in `llm/`.
- **JSON response parsing**: Shared `_parse_review()` in `LLMProvider` base class handles markdown fences, malformed items, and invalid severity gracefully.
- **Exception hierarchy**: `ProviderNotConfiguredError` / `ProviderError` replace `sys.exit()` control flow. CLI boundary catches and exits.
- **Config resolution order**: `--provider` CLI flag > `config.toml [provider].default` > auto-detect. API tokens always read from env vars (never in config files).
- **Severity blocking**: `Severity.blocks` property — `critical`/`error` return True (block commit), `warning`/`info` return False.
- **Prompt templates** in `prompts.py`: review prompt focuses on memory leaks, null pointer, race conditions, hardcoded secrets, buffer overflow. Explicitly excludes style/naming/refactoring suggestions.
- **Non-interactive mode**: `--auto-accept` flag or `AI_REVIEW_AUTO_ACCEPT=1` env var skips interactive prompt in commit-msg hook, auto-accepts AI suggestion.
- **Opt-in mechanism**: template hooks check `git config --local ai-review.enabled`; repos without opt-in are skipped entirely. No repo file pollution.
- **File extension filter**: `review.include_extensions` config (default: `c,cpp,h,hpp,java`); only matching files are sent to LLM.
- **Custom review rules**: `review.custom_rules` config (optional); natural language string appended to default BSP review prompt as additional rules. Set via `ai-review config set review custom_rules "..."`. When unset, behavior is identical to before.
- **Diff size limit**: `review.max_diff_lines` config (default: 2000); diffs exceeding the limit are truncated with a notice before sending to LLM.
- **HTTP retry**: Ollama/Enterprise use `httpx.HTTPTransport(retries=3)`, OpenAI SDK uses `max_retries=3`. Configurable timeout per provider (default: 120s).
- **Health check**: `health_check()` returns `tuple[bool, str]` with failure reason. `ai-review health-check` command validates connectivity.
- **Verbose mode**: `--verbose` / `-v` flag enables DEBUG logging for troubleshooting.

## Testing Conventions

- `respx` mocks HTTP for Ollama and Enterprise providers (httpx-based)
- `unittest.mock` patches OpenAI SDK client
- `click.testing.CliRunner` for CLI integration tests
- `tmp_path` + real `git init` for git.py and hook tests
- Global hook tests mock `subprocess.run` and `_GLOBAL_HOOKS_DIR`
- No real LLM API calls in any test
