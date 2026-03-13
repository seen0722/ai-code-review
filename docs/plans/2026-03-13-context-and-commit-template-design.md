# Hybrid Review Context + Interactive Commit Message Template

Date: 2026-03-13

## Background

Two key limitations identified in the current ai-review tool:

1. **AI review false positives** — LLM only sees `git diff --cached` (3 lines of context), lacking full file context. Reports issues like "memory leak" when `free()` exists in a cleanup function the LLM cannot see. Engineers lose trust and start using `--no-verify`.

2. **Commit message generation too vague** — AI generates generic descriptions from diff alone (e.g., "set gpio-pin to 0" instead of describing the hardware intent). Engineers still need to manually type commit messages, especially for device tree / config changes.

## Part 1: Hybrid Review Context

### Problem

Current `get_staged_diff()` returns `git diff --cached` output with default 3-line context. LLM cannot see:
- Cleanup functions / error paths in the same file
- struct/type definitions
- Caller context and ownership patterns
- Lock/mutex declarations in headers

Result: high false positive rate, especially for memory management and resource lifecycle patterns common in C/C++ BSP code.

### Industry Research

| Strategy | Description | Complexity |
|----------|-------------|------------|
| Hybrid context (diff + selective files) | Send diff + full files or functions involved | Medium |
| Code graph + vector DB (CodeRabbit) | Build dependency graph, retrieve relevant chunks via embeddings | High |
| Multi-model consensus | Send diff to multiple LLM variants, take intersection | High |
| Prompt improvement (CoT) | Chain of Thought prompting, explicit confidence thresholds | Low |

Sources: [Graphite](https://graphite.com/guides/ai-code-review-context-full-repo-vs-diff), [CodeRabbit](https://www.coderabbit.ai/blog/context-engineering-ai-code-reviews), [LAURA paper](https://www.arxiv.org/pdf/2512.01356), [diffray](https://diffray.ai/blog/llm-hallucinations-code-review/)

### Chosen Approach: Hybrid Context + Prompt Improvement

Given the constraints (enterprise internal LLM, unknown context window, small diffs of 1-3 files):

#### 1. Expand context sent to LLM

For each file in the staged diff:
- Read the **staged version** of the complete file via `git show :<filepath>` (not the working tree copy, which may have unstaged changes)
- Attach as additional context after the diff

**Context budget:** `review.max_context_lines` (default: 5000) controls the total lines of file context appended. This is **separate from** `review.max_diff_lines` (default: 2000) which limits the diff itself. The combined input to the LLM is at most `max_diff_lines + max_context_lines` lines.

**Fallback cascade** when total file content exceeds `max_context_lines`:
1. Only the **complete functions** that contain changed lines (detected by simple brace-counting heuristic for C/C++/Java — find enclosing `{` `}` block around changed line numbers)
2. If still too large, fall back to diff-only (current behavior)
3. Log a warning when fallback occurs so engineers can tune limits

**Pre-push path:** `pre_push_cmd()` uses `get_push_diff()` which operates on committed code, not staged. Hybrid context applies by reading files at the commit SHA via `git show <sha>:<filepath>` instead of `git show :<filepath>`.

#### 2. Improve review prompt

Update `_REVIEW_PROMPT` to include Chain of Thought guidance:

```
When reviewing, follow these steps:
1. Read the full file context to understand the complete function, struct definitions, and resource lifecycle
2. Check if the issue you found is already handled elsewhere in the file (cleanup functions, error paths, caller checks)
3. Only report an issue if you are confident it is a real problem based on the full context available
4. If the context is insufficient to confirm a problem, do not report it
```

#### Files Changed

| File | Change |
|------|--------|
| `git.py` | Add `get_staged_file_contents(extensions)` — returns dict of `{filepath: content}` for staged files |
| `prompts.py` | Update `_REVIEW_PROMPT` with CoT guidance; add `get_review_prompt_with_context()` that formats diff + file contents |
| `reviewer.py` | Update `review_diff()` to accept optional file contents and build enhanced prompt |
| `cli.py` | Call `get_staged_file_contents()` and pass to reviewer |
| `config.py` | Add `DEFAULT_MAX_CONTEXT_LINES = 5000` |

---

## Part 2: Interactive Commit Message Template

### Problem

AI-generated commit messages from diff are too vague for BSP work. Device tree changes, config modifications, and hardware-specific fixes require domain context that is not in the code — it is in the engineer's head.

### Solution: Structured Q&A Flow

Replace the current auto-generate approach with an interactive template system that:
1. Asks the engineer structured questions
2. AI formats, polishes English grammar, and assembles the final commit message
3. `modified:` file list is auto-generated from staged diff

### Commit Message Format

#### Title

```
(\[UPDATE\])?\[(BSP|CP|AP)\]\[[A-Z]+\] summary
```

Examples:
```
[BSP][CAMERA] fix boot hang caused by incorrect reset GPIO config
[UPDATE][AP][NAL] Built-in TrimbleInstallationManager app
[CP][AUDIO] add mixer path for headphone jack detection
```

#### Body — Three Sections (both feature and bugfix)

```
[IMPACT PROJECTS]
(user input)

[DESCRIPTION]
(content varies by type — see below)

modified:
(auto-generated from staged diff)

[TEST]
(user input)
```

#### `[DESCRIPTION]` Content by Type

**Feature:**
```
[DESCRIPTION]
Free-form description of the feature (user input, AI polishes English)

modified:
path/to/changed/file1
path/to/changed/file2
```

**Bugfix:**
```
[DESCRIPTION]
BUG-ID: JIRA-12345
SYMPTOM: EVT2 board hangs during boot at camera probe
ROOT CAUSE: Reset GPIO pin held high due to incorrect device tree configuration
SOLUTION: Set gpio-pin to 0 (active-low reset) in camera device tree node

modified:
arch/arm64/boot/dts/vendor/camera-sensor.dtsi
```

### Interactive Q&A Flow

#### Feature Flow

```
$ git commit

ai-review: Commit message template

New or update? [i]nit / [u]pdate: i
Type? [f]eature / [b]ugfix: f
Category? [BSP] / [CP] / [AP]: AP
Component? CAMERA / AUDIO / NAL / ... / (custom): NAL
Summary? > Built-in TrimbleInstallationManager app
Impact projects? > LINUX/android/vendor/qcom/proprietary/
Description? > Add flag to copy apk from source
Test? > 1. Build successfully 2. Can lunch app

---
[AP][NAL] Built-in TrimbleInstallationManager app

[IMPACT PROJECTS]
LINUX/android/vendor/qcom/proprietary/

[DESCRIPTION]
Add flag LOCAL_REPLACE_PREBUILT_APK_INSTALLED to copy apk from source

modified:
prebuilt/TrimbleInstallationManager/Android.mk

[TEST]
1. Build successfully
2. Can lunch TrimbleInstallationManager app successfully

[A]ccept / [E]dit / [S]kip:
```

#### Bugfix Flow

```
$ git commit

ai-review: Commit message template

New or update? [i]nit / [u]pdate: i
Type? [f]eature / [b]ugfix: b
Category? [BSP] / [CP] / [AP]: BSP
Component? CAMERA / AUDIO / ... / (custom): CAMERA
Summary? > fix boot hang caused by incorrect reset GPIO
Impact projects? > LINUX/kernel/drivers/media/
Bug ID? > JIRA-12345
Symptom? > EVT2 board hangs during boot at camera probe
Root cause? > reset GPIO pin held high
Solution? > set gpio-pin to 0
Test? > 1. Boot success on EVT2/EVT3 2. Camera preview OK

---
[BSP][CAMERA] fix boot hang caused by incorrect reset GPIO config

[IMPACT PROJECTS]
LINUX/kernel/drivers/media/

[DESCRIPTION]
BUG-ID: JIRA-12345
SYMPTOM: EVT2 board hangs during boot at camera probe
ROOT CAUSE: Reset GPIO pin held high due to incorrect device tree configuration
SOLUTION: Set gpio-pin to 0 (active-low reset) in camera device tree node

modified:
arch/arm64/boot/dts/vendor/camera-sensor.dtsi

[TEST]
1. Boot success on EVT2/EVT3
2. Camera preview OK

[A]ccept / [E]dit / [S]kip:
```

### AI's Role

1. **Polish English** — fix grammar/spelling in user-provided text (summary, description, symptom, root cause, solution, test)
2. **Enrich with diff context** — use staged diff to add specific details (e.g., user types "add flag to copy apk" → AI adds the actual flag name `LOCAL_REPLACE_PREBUILT_APK_INSTALLED`)
3. **Auto-generate `modified:` list** — extract file paths from staged diff
4. **Format** — assemble all sections into the final commit message

### `-m` Flag Handling

When engineer uses `git commit -m "..."`, the prepare-commit-msg hook receives `source="message"`. Current code skips for this case. New behavior:
- Remove `"message"` from the skip list so the interactive Q&A triggers even with `-m`
- The original `-m` message is ignored in favor of the structured Q&A flow
- Keep skipping for `source="merge"`, `"squash"`, `"commit"` (amend)

### Non-Interactive Fallback

When stdin is not a TTY (IDE, CI, scripted commits):
- Skip the interactive Q&A entirely
- Fall back to current auto-generate behavior (AI generates from diff)
- Detection: `sys.stdin.isatty()` check at the start of the Q&A flow
- `--auto-accept` flag also skips Q&A and uses auto-generate

### Configuration

```toml
[commit]
# Replace old project_id
default_category = "BSP"                    # pre-select category (optional)
components = "CAMERA,AUDIO,DISPLAY,SENSOR,POWER,THERMAL,MEMORY,STORAGE,NAL"
```

### Format Validation

Update `commit_check.py` regex from:
```python
# Old
r"^\[[A-Z]+-\d+\] .+"
```
To:
```python
# New
r"^(\[UPDATE\])?\[(BSP|CP|AP)\]\[[A-Z]+\] .+"
```

### Files Changed

| File | Change |
|------|--------|
| `commit_check.py` | Update regex to new format |
| `cli.py` | Replace `generate_commit_msg_cmd()` with interactive Q&A flow; update prepare-commit-msg hook behavior; add `sys.stdin.isatty()` fallback |
| `prompts.py` | Update `_COMMIT_IMPROVE_PROMPT` to reference new `[CATEGORY][COMPONENT]` format instead of `[PROJECT-NUMBER]`; add commit message polishing prompt (takes user inputs + diff, returns polished text) |
| `reviewer.py` | Add `compose_commit_message()` method |
| `config.py` | Add `default_category`, `components` config keys; deprecation warning if `commit.project_id` is found |
| `commit_template.py` | New file — template definitions, Q&A flow logic, message assembly |

### Breaking Changes

- `[PROJECT-NUMBER] description` format replaced by `(\[UPDATE\])?[CATEGORY][COMPONENT] description`
- `commit.project_id` config deprecated → replaced by `commit.default_category`. If old key is found, print deprecation warning
- `generate-commit-msg` command behavior changes from auto-generate to interactive Q&A (with auto-generate fallback for non-TTY)
- Format validation regex updated
- `_COMMIT_IMPROVE_PROMPT` updated to reference new format

### Migration

- Existing `commit.project_id` config: print warning on first use, suggest migration command
- Old-format commit messages in existing repos: not affected (validation only applies to new commits)
- Component list: custom input is accepted and used as-is (not persisted to config); to add permanently, use `ai-review config set commit components "..."`

---

## Scope Summary

| Area | Effort | Risk |
|------|--------|------|
| Hybrid review context | Medium | Low — additive change, fallback to current behavior |
| Prompt CoT improvement | Low | Low — prompt-only change |
| Interactive commit template | Medium-High | Medium — changes existing hook behavior, breaking format change |
| Format validation update | Low | Low — regex change |

## Out of Scope

- Code graph / vector DB (too heavy for current needs)
- Multi-model consensus (requires multiple LLM instances)
- CI/CD pipeline integration
- Dashboard / statistics for review results
