# ai-code-review

AI-powered code review CLI for Android BSP teams. Catches serious defects (memory leaks, race conditions, null pointers, hardcoded secrets) before commit and enforces unified commit message format.

## Features

- **AI code review** — Automatically review staged git diff for critical issues
- **Commit message enforcement** — Validates `[PROJECT-NUMBER] description` format
- **AI commit message improvement** — Fixes English grammar and clarifies descriptions
- **Multiple LLM backends** — Ollama (local), enterprise internal LLM, OpenAI
- **Template hooks** — One command to enable across all repos via `init.templateDir`
- **Custom review rules** — Add project-specific checks via config, no code changes needed
- **Multiple output formats** — Terminal (colored), Markdown, JSON
- **Health check** — Validate LLM provider connectivity before first use
- **HTTP retry** — Automatic retry (3 attempts) for transient network errors
- **Configurable timeout** — Per-provider timeout settings
- **Diff size limit** — Prevents LLM context window overflow with large diffs
- **Verbose mode** — Debug logging for troubleshooting

## Installation

### Prerequisites

- Python 3.10+ (`python3 --version`)
- Git (`git --version`)
- pip (`pip --version`)

If Python 3.10+ is not installed:

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-pip python3-venv

# macOS (Homebrew)
brew install python@3.12
```

### Install from source

```bash
# GitHub
git clone https://github.com/seen0722/ai-code-review.git

# Or internal GitLab (replace with your URL)
# git clone https://gitlab.internal.company.com/bsp-tools/ai-code-review.git

cd ai-code-review
pip install .
```

Alternatively, install directly without cloning:

```bash
pip install git+https://github.com/seen0722/ai-code-review.git
```

Verify: `ai-review --help`

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

### 2. Install hooks

```bash
ai-review hook install --template
```

This sets `init.templateDir` so new clones auto-get hooks. For existing repos:

```bash
repo forall -c 'git init'    # Android repo projects
```

### 3. Enable repos (opt-in)

Hooks only activate in repos with `ai-review.enabled = true` (stored in `.git/config`, no repo file pollution):

```bash
ai-review hook enable                        # enable current repo
ai-review hook disable                       # disable current repo
repo forall -c 'ai-review hook enable'       # batch enable (Android repo)
```

Every `git commit` in enabled repos will automatically:

1. Run AI code review on staged changes (blocks on critical/error)
2. Validate commit message format `[PROJECT-NUMBER] description`
3. Improve English grammar/clarity via AI (auto-accepted)

### 4. Verify setup

```bash
ai-review health-check            # validate LLM provider connectivity
ai-review config show             # view current configuration
```

### 5. Review code manually

```bash
git add -A
ai-review                         # terminal output (default)
ai-review -v                      # review with debug logging
ai-review --format markdown       # markdown report
ai-review --format json           # structured JSON
```

## Hook Management

```bash
# Template hooks (recommended)
ai-review hook install --template      # install via init.templateDir
ai-review hook uninstall --template    # remove template hooks

# Per-repo hooks
ai-review hook install pre-commit      # install for current repo only
ai-review hook install commit-msg
ai-review hook uninstall pre-commit
ai-review hook uninstall commit-msg

# Opt-in control
ai-review hook enable                  # enable current repo
ai-review hook disable                 # disable current repo
ai-review hook status                  # show hook status

# Skip hooks for a single commit
git commit --no-verify -m "[HOTFIX-001] emergency fix"
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

## Custom Review Rules

Add project-specific review rules without modifying source code:

```bash
ai-review config set review custom_rules "Also check for integer overflow, use-after-free, and double-free"
```

Custom rules are appended to the default BSP review prompt. When not set, behavior is unchanged.

## Configuration

Config file location: `~/.config/ai-code-review/config.toml`

API keys and tokens are read from environment variables (never stored in config files).

```bash
ai-review config show             # view all settings
ai-review config show openai      # view single section
ai-review config set <section> <key> <value>
ai-review config get <section> <key>
```

### Additional config options

| Option | Default | Description |
|--------|---------|-------------|
| `review.include_extensions` | `c,cpp,h,hpp,java` | File extensions to review |
| `review.custom_rules` | (none) | Additional review rules in natural language |
| `review.max_diff_lines` | `2000` | Max diff lines sent to LLM (truncated if exceeded) |
| `<provider>.timeout` | `120` | HTTP timeout in seconds per provider |

## Severity Levels

| Level | Meaning | Blocks commit |
|-------|---------|---------------|
| critical | Security vulnerabilities, data leaks | Yes |
| error | Obvious bugs, logic errors | Yes |
| warning | Potential issues | No |
| info | General suggestions | No |
