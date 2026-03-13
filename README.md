# ai-code-review

AI-powered code review CLI for Android BSP teams. Catches serious defects (memory leaks, race conditions, null pointers, hardcoded secrets) before commit and enforces unified commit message format.

## Features

- **AI code review** — Automatically review staged git diff for critical issues
- **Hybrid review context** — Sends full file contents alongside diffs for fewer false positives
- **Commit message enforcement** — Validates `[CATEGORY][COMPONENT] summary` format
- **Interactive commit message template** — Structured Q&A flow generates formatted commit messages with AI polishing
- **AI commit message improvement** — Fixes English grammar and clarifies descriptions
- **Pre-push review** — AI reviews all commits before push as a last line of defense
- **Graceful degradation** — LLM failures warn but never block development workflow
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

1. Run AI code review on staged changes with full file context (blocks on critical/error)
2. Run interactive Q&A to generate structured commit message (if no `-m` provided and TTY available)
3. Validate commit message format `[CATEGORY][COMPONENT] summary`
4. Improve English grammar/clarity via AI (auto-accepted)

Every `git push` will review all commits being pushed as a final check.

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
ai-review hook install pre-commit          # install for current repo only
ai-review hook install prepare-commit-msg
ai-review hook install commit-msg
ai-review hook install pre-push
ai-review hook uninstall pre-commit
ai-review hook uninstall prepare-commit-msg
ai-review hook uninstall commit-msg
ai-review hook uninstall pre-push

# Opt-in control
ai-review hook enable                  # enable current repo
ai-review hook disable                 # disable current repo
ai-review hook status                  # show hook status

# Skip hooks for a single commit
git commit --no-verify -m "[HOTFIX-001] emergency fix"
```

## Commit Message Format

All commit messages must follow: `[CATEGORY][COMPONENT] summary`

- **Categories**: BSP, CP, AP
- **Component**: uppercase identifier (e.g., CAMERA, AUDIO, DISPLAY)
- **Optional prefix**: `[UPDATE]` for follow-up commits

Examples:
```
[BSP][CAMERA] fix null pointer crash in preview callback
[AP][NAL] add installation manager retry logic
[UPDATE][CP][AUDIO] update mixer path for headset detection
```

The commit body uses structured sections:
```
[BSP][CAMERA] fix null pointer crash in preview callback

[IMPACT PROJECTS]
camera-hal, framework/av

[DESCRIPTION]
BUG-ID: CAM-1234
SYMPTOM: Camera preview crashes on boot
ROOT CAUSE: Null pointer in frame callback when buffer is not allocated
SOLUTION: Add null check before accessing buffer pointer

modified:
hardware/camera/hal/preview.cpp
hardware/camera/hal/buffer.h

[TEST]
Boot device, open camera, verify preview starts without crash
```

When using the prepare-commit-msg hook with TTY, an interactive Q&A guides you through filling each section. AI polishes your summary and description for clarity.

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
| `review.max_context_lines` | `5000` | Max lines of full file context sent alongside diff |
| `commit.default_category` | (none) | Default category for interactive Q&A (BSP/CP/AP) |
| `commit.components` | (none) | Comma-separated custom component list for Q&A |
| `<provider>.timeout` | `120` | HTTP timeout in seconds per provider |

Note: `commit.project_id` is deprecated. Use `commit.default_category` instead.

## Severity Levels

| Level | Meaning | Blocks commit |
|-------|---------|---------------|
| critical | Security vulnerabilities, data leaks | Yes |
| error | Obvious bugs, logic errors | Yes |
| warning | Potential issues | No |
| info | General suggestions | No |
