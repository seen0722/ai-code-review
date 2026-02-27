# ai-code-review

AI-powered code review CLI for Android BSP teams. Catches serious defects (memory leaks, race conditions, null pointers, hardcoded secrets) before commit and enforces unified commit message format.

## Features

- **AI code review** — Automatically review staged git diff for critical issues
- **Commit message enforcement** — Validates `[PROJECT-NUMBER] description` format
- **AI commit message improvement** — Fixes English grammar and clarifies descriptions
- **Multiple LLM backends** — Ollama (local), enterprise internal LLM, OpenAI
- **Global hooks** — One command to enable across all repos (ideal for hundreds of repos)
- **Multiple output formats** — Terminal (colored), Markdown, JSON

## Installation

```bash
pip install ai-code-review
```

## Quick Start

### 1. Configure a provider

```bash
# Local Ollama (recommended for offline/internal use)
ai-review config set provider default ollama
ai-review config set ollama base_url http://localhost:11434
ai-review config set ollama model codellama

# Enterprise LLM
ai-review config set provider default enterprise
ai-review config set enterprise base_url https://llm.internal.company.com
ai-review config set enterprise api_path /v1/chat/completions
ai-review config set enterprise model internal-codellama-70b
ai-review config set enterprise auth_type bearer
ai-review config set enterprise auth_token_env ENTERPRISE_LLM_KEY

# OpenAI
ai-review config set provider default openai
ai-review config set openai api_key_env OPENAI_API_KEY
ai-review config set openai model gpt-4o
```

### 2. Enable hooks globally (recommended)

One command enables AI review for **all** git repos on the machine:

```bash
ai-review hook install --global
```

This creates hook scripts at `~/.config/ai-code-review/hooks/` and sets `git config --global core.hooksPath` to point there. Every `git commit` in any repo will now automatically:

1. Run AI code review on staged changes (blocks on critical/error)
2. Validate commit message format `[PROJECT-NUMBER] description`
3. Suggest AI-powered grammar/clarity improvements (auto-accepted)

### 3. Review code manually

```bash
git add -A
ai-review                         # terminal output (default)
ai-review --format markdown       # markdown report
ai-review --format json           # structured JSON
```

## Hook Setup

### Global hooks (recommended for multi-repo teams)

```bash
# Install — enables hooks for ALL repos
ai-review hook install --global

# Check status
ai-review hook status

# Uninstall — removes hooks and restores default behavior
ai-review hook uninstall --global
```

**Managing exceptions:**

```bash
# Disable for a single repo
cd /path/to/repo
git config core.hooksPath .git/hooks

# Skip hooks for a single commit
git commit --no-verify
```

### Per-repo hooks

```bash
# Install hooks for current repo only
ai-review hook install pre-commit
ai-review hook install commit-msg

# Uninstall
ai-review hook uninstall pre-commit
ai-review hook uninstall commit-msg
```

### pre-commit framework

If your team uses the [pre-commit](https://pre-commit.com) framework, add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/seen0722/ai-code-review
    rev: v0.1.0
    hooks:
      - id: ai-review-commit-msg
      - id: ai-review-code
        args: ["--provider", "ollama"]
```

Then install:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Commit Message Format

All commit messages must follow: `[PROJECT-NUMBER] description`

Examples:
```
[BSP-456] fix camera HAL crash on boot
[KERN-789] update device tree for new display panel
[AUD-012] resolve ALSA mixer channel switching issue
```

When using the commit-msg hook, AI will suggest grammar and clarity improvements automatically.

## Configuration

Config file location: `~/.config/ai-code-review/config.toml`

API keys and tokens are read from environment variables (never stored in config files).

## Severity Levels

| Level | Meaning | Blocks commit |
|-------|---------|---------------|
| critical | Security vulnerabilities, data leaks | Yes |
| error | Obvious bugs, logic errors | Yes |
| warning | Potential issues | No |
| info | General suggestions | No |
