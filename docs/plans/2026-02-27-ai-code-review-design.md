# AI Code Review — Design Document

## Overview

A Python CLI tool (`ai-review`) that provides AI-powered code review and commit message quality enforcement for Android BSP engineering teams. Designed for teams that push directly to main branch across hundreds of GitLab repos on an internal network.

## Goals

- Catch serious code defects (memory leaks, race conditions, null pointers, hardcoded secrets) before commit
- Enforce unified commit message format: `[PROJECT-NUMBER] description`
- AI-assisted English grammar correction and description improvement for commit messages
- Zero workflow disruption — integrates via pre-commit framework
- Support multiple LLM backends: local Ollama, enterprise LLM, external OpenAI

## Non-Goals (v1)

- Custom review rules via config files
- GitLab MR / CI pipeline integration
- Code style or naming suggestions
- Refactoring recommendations

## CLI Interface

```bash
# Default: review staged diff
ai-review

# Specify provider / model
ai-review --provider ollama --model codellama

# Specify output format
ai-review --format terminal|markdown|json

# Check commit message only
ai-review check-commit

# Configuration
ai-review config set provider ollama
ai-review config set ollama.base_url http://localhost:11434

# Hook management (for users not using pre-commit framework)
ai-review hook install pre-commit
ai-review hook uninstall pre-commit
ai-review hook status
```

## Pre-commit Flow

```
git commit -m "[BSP-456] fix camera HAL crash when boot"
  │
  ├─ Step 1: Commit message format check (regex, milliseconds)
  │   ✗ Missing [PROJECT-NUMBER] → block, show correct format
  │   ✓ Format correct → continue
  │
  ├─ Step 2: AI commit description improvement (LLM call)
  │   → Fix English grammar + clarify description based on staged diff
  │   → Show suggestion:
  │     Original: [BSP-456] fix camera HAL crash when boot
  │     Suggested: [BSP-456] fix camera HAL crash during boot sequence
  │   → User chooses: [A]ccept / [E]dit / [S]kip
  │
  └─ Step 3: AI code review (LLM call, seconds)
      ✗ critical/error → block commit
      ✓ No severe issues → commit succeeds (warning/info shown but not blocking)
```

## Severity Levels

| Level | Meaning | Blocks commit |
|-------|---------|---------------|
| critical | Security vulnerabilities, data leaks | Yes |
| error | Obvious bugs, logic errors | Yes |
| warning | Potential issues worth noting | No |
| info | General suggestions | No |

## LLM Provider Architecture

### Unified Interface

```python
class LLMProvider(ABC):
    @abstractmethod
    def review_code(self, diff: str, prompt: str) -> ReviewResult: ...

    @abstractmethod
    def improve_commit_msg(self, message: str, diff: str) -> str: ...

    @abstractmethod
    def health_check(self) -> bool: ...
```

### Providers

| Provider | Use case | API format |
|----------|----------|------------|
| ollama | Local dev, offline | Ollama REST API (`/api/chat`) |
| enterprise | Internal company LLM | Configurable base URL + auth |
| openai | External OpenAI or compatible API | OpenAI SDK |

### Provider Selection Priority

```
CLI --provider flag > config.toml [provider].default > auto-detect
```

Auto-detect: check local Ollama → check enterprise env var → check OpenAI env var → prompt user.

### Configuration

```toml
# ~/.config/ai-code-review/config.toml

[provider]
default = "ollama"

[ollama]
base_url = "http://localhost:11434"
model = "codellama"

[enterprise]
base_url = "https://llm.internal.company.com"
api_path = "/v1/chat/completions"
model = "internal-codellama-70b"
auth_type = "bearer"                  # bearer / api-key / custom-header
auth_token_env = "ENTERPRISE_LLM_KEY" # read token from env var

[openai]
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o"
```

API keys/tokens are always read from environment variables, never stored in config files.

## Prompts

### Commit Message Improvement

Focus: fix English grammar, make description accurately reflect the diff, keep under 72 chars, preserve `[PROJECT-NUMBER]` prefix.

### Code Review

Focus areas for Android BSP:
- Memory leaks (malloc without free, unreleased resources)
- Null pointer dereference
- Race conditions, missing lock protection
- Hardcoded secrets (keys, passwords, tokens)
- Obvious logic errors
- Buffer overflow

Explicitly excluded: code style, naming, performance optimization, refactoring suggestions.

## Output Formats

### Terminal (default)

Colored output via `rich` — red for critical/error, yellow for warning. Shows summary and whether commit is blocked.

### Markdown

Table format with severity, file, line, issue columns.

### JSON

Structured output with summary counts, blocked status, and issues array. For future integration with CI dashboards or notification systems.

## Project Structure

```
ai-code-review/
├── pyproject.toml
├── README.md
├── .pre-commit-hooks.yaml
├── src/ai_code_review/
│   ├── __init__.py
│   ├── cli.py
│   ├── git.py
│   ├── commit_check.py
│   ├── reviewer.py
│   ├── prompts.py
│   ├── formatters.py
│   ├── config.py
│   └── llm/
│       ├── __init__.py
│       ├── base.py
│       ├── openai.py
│       ├── ollama.py
│       └── enterprise.py
└── tests/
    ├── test_commit_check.py
    ├── test_git.py
    ├── test_reviewer.py
    ├── test_formatters.py
    └── test_llm/
        ├── test_openai.py
        ├── test_ollama.py
        └── test_enterprise.py
```

## Tech Stack

| Purpose | Package | Reason |
|---------|---------|--------|
| CLI framework | click | Mature, good subcommand support |
| Terminal output | rich | Colors, tables, formatting |
| HTTP client | httpx | Async support, modern |
| Config | tomli + tomli-w | Standard TOML handling |
| OpenAI | openai | Official SDK |
| Testing | pytest | Standard |
| Packaging | hatchling | Modern Python packaging with pyproject.toml |

## pre-commit Framework Integration

```yaml
# .pre-commit-hooks.yaml (provided by this repo)
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

Consumer repos add to their `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://gitlab.internal.company.com/devops/ai-code-review
    rev: v0.1.0
    hooks:
      - id: ai-review-commit-msg
      - id: ai-review-code
        args: ["--provider", "ollama"]
```

## Deployment

```bash
# Install from internal PyPI
pip install ai-code-review --index-url https://pypi.internal.company.com/simple/

# Or direct install
pip install ai-code-review
```
