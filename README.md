# ai-code-review

AI-powered code review CLI for Android BSP teams. Catches serious defects (memory leaks, race conditions, null pointers, hardcoded secrets) before commit and enforces unified commit message format.

## Features

- **AI code review** — Automatically review staged git diff for critical issues
- **Commit message enforcement** — Validates `[PROJECT-NUMBER] description` format
- **AI commit message improvement** — Fixes English grammar and clarifies descriptions
- **Multiple LLM backends** — Ollama (local), enterprise internal LLM, OpenAI
- **pre-commit framework integration** — Zero-friction setup across hundreds of repos
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

### 2. Review code

```bash
git add -A
ai-review
```

### 3. Output formats

```bash
ai-review --format terminal    # default, colored output
ai-review --format markdown    # markdown report
ai-review --format json        # structured JSON
```

## pre-commit Framework Integration

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://gitlab.internal.company.com/devops/ai-code-review
    rev: v0.1.0
    hooks:
      - id: ai-review-commit-msg
      - id: ai-review-code
        args: ["--provider", "ollama"]
```

Then run:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Manual Hook Installation

For teams not using pre-commit framework:

```bash
ai-review hook install pre-commit
ai-review hook install commit-msg
ai-review hook status
```

## Commit Message Format

All commit messages must follow: `[PROJECT-NUMBER] description`

Examples:
```
[BSP-456] fix camera HAL crash on boot
[KERN-789] update device tree for new display panel
[AUD-012] resolve ALSA mixer channel switching issue
```

When using the commit-msg hook, AI will also suggest grammar and clarity improvements interactively.

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
