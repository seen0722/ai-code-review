# Hybrid Review Context + Interactive Commit Template — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce AI review false positives by sending full file context to LLM, and replace vague auto-generated commit messages with a structured interactive Q&A template matching the team's existing commit format.

**Architecture:** Two independent parts. Part 1 adds a new `get_staged_file_contents()` function in git.py, updates the review prompt with Chain of Thought guidance, and threads file context through reviewer.py → cli.py. Part 2 creates a new `commit_template.py` module for template definitions and Q&A flow, updates `commit_check.py` regex to the new `[CATEGORY][COMPONENT]` format, and rewires `generate_commit_msg_cmd()` in cli.py to use the interactive flow.

**Tech Stack:** Python 3.10+, click (CLI), rich (terminal), httpx, pytest + respx + pytest-mock

**Design spec:** `docs/plans/2026-03-13-context-and-commit-template-design.md`

---

## Chunk 1: Part 1 — Hybrid Review Context

### Task 1: Add `get_staged_file_contents()` to git.py

**Files:**
- Modify: `src/ai_code_review/git.py`
- Test: `tests/test_git.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_git.py — add to existing file

class TestGetStagedFileContents:
    """Tests for get_staged_file_contents()."""

    def test_returns_file_contents_for_staged_files(self, tmp_path):
        """Staged .c file content is returned via git show."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
        # Initial commit so HEAD exists
        (repo / "dummy.txt").write_text("init")
        subprocess.run(["git", "add", "dummy.txt"], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
        # Stage a .c file
        c_file = repo / "main.c"
        c_file.write_text("int main() { return 0; }\n")
        subprocess.run(["git", "add", "main.c"], cwd=repo, capture_output=True)

        with patch("ai_code_review.git._run_git") as mock_git:
            # Mock diff --cached --name-only to return staged file list
            # Mock git show :filepath to return file content
            def side_effect(*args):
                if args[:2] == ("diff", "--cached") and "--name-only" in args:
                    return "main.c\n"
                if args[:2] == ("show", ":main.c"):
                    return "int main() { return 0; }\n"
                return ""
            mock_git.side_effect = side_effect

            from ai_code_review.git import get_staged_file_contents
            result = get_staged_file_contents(extensions=["c"])
            assert "main.c" in result
            assert "int main()" in result["main.c"]

    def test_filters_by_extension(self, tmp_path):
        """Only files matching extensions are returned."""
        with patch("ai_code_review.git._run_git") as mock_git:
            def side_effect(*args):
                if "--name-only" in args:
                    return "main.c\nREADME.md\nutils.h\n"
                if args[1] == ":main.c":
                    return "int main() {}\n"
                if args[1] == ":utils.h":
                    return "void util();\n"
                return ""
            mock_git.side_effect = side_effect

            from ai_code_review.git import get_staged_file_contents
            result = get_staged_file_contents(extensions=["c", "h"])
            assert "main.c" in result
            assert "utils.h" in result
            assert "README.md" not in result

    def test_returns_empty_when_no_staged_files(self):
        """Returns empty dict when nothing is staged."""
        with patch("ai_code_review.git._run_git") as mock_git:
            mock_git.return_value = ""
            from ai_code_review.git import get_staged_file_contents
            result = get_staged_file_contents(extensions=["c"])
            assert result == {}

    def test_respects_max_lines(self):
        """Stops adding files when total lines exceed max_lines."""
        with patch("ai_code_review.git._run_git") as mock_git:
            big_content = "\n".join(f"line {i}" for i in range(100))
            small_content = "int x = 1;\n"
            def side_effect(*args):
                if "--name-only" in args:
                    return "big.c\nsmall.c\n"
                if args[1] == ":big.c":
                    return big_content
                if args[1] == ":small.c":
                    return small_content
                return ""
            mock_git.side_effect = side_effect

            from ai_code_review.git import get_staged_file_contents
            result = get_staged_file_contents(extensions=["c"], max_lines=50)
            # big.c included (at least one file always included)
            assert "big.c" in result
            # small.c excluded (over budget after big.c)
            assert "small.c" not in result

    def test_get_commit_file_contents(self):
        """Reads file contents at a specific commit SHA."""
        with patch("ai_code_review.git._run_git") as mock_git:
            def side_effect(*args):
                if "diff-tree" in args:
                    return "main.c\n"
                if args[:2] == ("show", "abc123:main.c"):
                    return "int main() {}\n"
                return ""
            mock_git.side_effect = side_effect

            from ai_code_review.git import get_commit_file_contents
            result = get_commit_file_contents("abc123", extensions=["c"])
            assert "main.c" in result
            assert "int main()" in result["main.c"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_git.py::TestGetStagedFileContents -v`
Expected: FAIL — `ImportError: cannot import name 'get_staged_file_contents'`

- [ ] **Step 3: Implement `get_staged_file_contents()` and `get_commit_file_contents()`**

Add to `src/ai_code_review/git.py` after `get_push_diff()`:

```python
def _get_file_contents(
    file_list_cmd: list[str],
    show_prefix: str,
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Read file contents from git, filtered by extension.

    Args:
        file_list_cmd: git args to list files (e.g., ["diff", "--cached", "--name-only"])
        show_prefix: prefix for git show (e.g., ":" for staged, "abc123:" for commit)
        extensions: file extension filter
        max_lines: stop adding files after this many total lines
    """
    raw = _run_git(*file_list_cmd).strip()
    if not raw:
        return {}

    files = [f for f in raw.split("\n") if f.strip()]
    if extensions:
        ext_set = {f".{e}" for e in extensions}
        files = [f for f in files if any(f.endswith(e) for e in ext_set)]

    result = {}
    total_lines = 0
    for filepath in files:
        try:
            content = _run_git("show", f"{show_prefix}{filepath}")
        except GitError:
            continue
        file_lines = content.count("\n") + 1
        if total_lines + file_lines > max_lines and result:
            break  # Over budget, stop (but include at least one file)
        result[filepath] = content
        total_lines += file_lines

    return result


def get_staged_file_contents(
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Return staged file contents via git show :filepath."""
    return _get_file_contents(
        file_list_cmd=["diff", "--cached", "--name-only"],
        show_prefix=":",
        extensions=extensions,
        max_lines=max_lines,
    )


def get_commit_file_contents(
    commit_sha: str,
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Return file contents at a specific commit SHA via git show sha:filepath."""
    return _get_file_contents(
        file_list_cmd=["diff-tree", "--no-commit-id", "-r", "--name-only", commit_sha],
        show_prefix=f"{commit_sha}:",
        extensions=extensions,
        max_lines=max_lines,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_git.py::TestGetStagedFileContents -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/git.py tests/test_git.py
git commit -m "feat: add get_staged_file_contents() for hybrid review context"
```

---

### Task 2: Update review prompt with Chain of Thought guidance

**Files:**
- Modify: `src/ai_code_review/prompts.py`
- Test: `tests/test_prompts.py`

**Dependencies:** None (independent, can run in parallel with Task 1)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_prompts.py — add to existing file

class TestReviewPromptWithContext:
    """Tests for get_review_prompt_with_context()."""

    def test_includes_cot_guidance(self):
        from ai_code_review.prompts import get_review_prompt_with_context
        prompt = get_review_prompt_with_context(
            file_contents={"main.c": "int main() { return 0; }"},
            custom_rules=None,
        )
        assert "follow these steps" in prompt
        assert "full file context" in prompt
        assert "confident it is a real problem" in prompt

    def test_includes_file_contents(self):
        from ai_code_review.prompts import get_review_prompt_with_context
        contents = {"driver.c": "void cleanup() { free(ptr); }"}
        prompt = get_review_prompt_with_context(
            file_contents=contents,
            custom_rules=None,
        )
        assert "driver.c" in prompt
        assert "void cleanup() { free(ptr); }" in prompt

    def test_includes_custom_rules(self):
        from ai_code_review.prompts import get_review_prompt_with_context
        prompt = get_review_prompt_with_context(
            file_contents={"a.c": "code"},
            custom_rules="Check for use-after-free",
        )
        assert "use-after-free" in prompt

    def test_empty_file_contents_returns_basic_prompt(self):
        from ai_code_review.prompts import get_review_prompt_with_context
        prompt = get_review_prompt_with_context(
            file_contents={},
            custom_rules=None,
        )
        # Should still have the base review prompt
        assert "senior Android BSP engineer" in prompt
        # But no CoT guidance since no context
        assert "follow these steps" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestReviewPromptWithContext -v`
Expected: FAIL — `ImportError: cannot import name 'get_review_prompt_with_context'`

- [ ] **Step 3: Implement prompt with context**

Add to `src/ai_code_review/prompts.py`:

```python
_COT_GUIDANCE = """\

When reviewing, follow these steps:
1. Read the full file context to understand the complete function, struct definitions, and resource lifecycle
2. Check if the issue you found is already handled elsewhere in the file (cleanup functions, error paths, caller checks)
3. Only report an issue if you are confident it is a real problem based on the full context available
4. If the context is insufficient to confirm a problem, do not report it"""


def get_review_prompt_with_context(
    file_contents: dict[str, str],
    custom_rules: str | None = None,
) -> str:
    """Build review prompt with full file context and CoT guidance."""
    if not file_contents:
        return get_review_prompt(custom_rules)

    base = get_review_prompt(custom_rules)
    # Insert CoT guidance before "Respond with a JSON array"
    base = base.replace(
        "\nRespond with a JSON array",
        _COT_GUIDANCE + "\n\nRespond with a JSON array",
    )

    # Append file contents section
    context_parts = ["\n\n--- Full file context ---"]
    for filepath, content in file_contents.items():
        context_parts.append(f"\n### {filepath}\n```\n{content}\n```")

    return base + "\n".join(context_parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestReviewPromptWithContext -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/prompts.py tests/test_prompts.py
git commit -m "feat: add review prompt with CoT guidance and file context"
```

---

### Task 3: Thread file context through reviewer.py and cli.py

**Files:**
- Modify: `src/ai_code_review/reviewer.py`
- Modify: `src/ai_code_review/cli.py`
- Modify: `src/ai_code_review/config.py`
- Test: `tests/test_reviewer.py`
- Test: `tests/test_cli.py`

**Dependencies:** Task 1, Task 2

- [ ] **Step 1: Write failing tests for reviewer**

```python
# tests/test_reviewer.py — add to existing file

class TestReviewDiffWithContext:
    """Tests for review_diff with file_contents parameter."""

    def test_passes_file_contents_to_prompt(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)

        file_contents = {"main.c": "int main() {}"}
        reviewer.review_diff("diff content", file_contents=file_contents)

        # Verify provider.review_code was called with a prompt containing file context
        call_args = provider.review_code.call_args
        prompt = call_args[0][1]  # second positional arg is prompt
        assert "main.c" in prompt
        assert "follow these steps" in prompt

    def test_no_file_contents_uses_basic_prompt(self):
        provider = MagicMock()
        provider.review_code.return_value = ReviewResult()
        reviewer = Reviewer(provider=provider)

        reviewer.review_diff("diff content")

        call_args = provider.review_code.call_args
        prompt = call_args[0][1]
        assert "follow these steps" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_reviewer.py::TestReviewDiffWithContext -v`
Expected: FAIL — `review_diff() got unexpected keyword argument 'file_contents'`

- [ ] **Step 3: Update reviewer.py**

```python
# src/ai_code_review/reviewer.py — update review_diff signature
from .prompts import get_review_prompt, get_review_prompt_with_context

def review_diff(
    self,
    diff: str,
    custom_rules: str | None = None,
    file_contents: dict[str, str] | None = None,
) -> ReviewResult:
    if file_contents:
        prompt = get_review_prompt_with_context(file_contents, custom_rules)
    else:
        prompt = get_review_prompt(custom_rules)
    return self._provider.review_code(diff, prompt)
```

- [ ] **Step 4: Add DEFAULT_MAX_CONTEXT_LINES to config.py**

```python
# src/ai_code_review/config.py — add after DEFAULT_MAX_DIFF_LINES
DEFAULT_MAX_CONTEXT_LINES = 5000
```

- [ ] **Step 5: Update cli.py `_review()` to pass file context**

In `src/ai_code_review/cli.py`, update `_review()` (around line 97):
- Import `get_staged_file_contents` and `get_commit_file_contents` from `.git`
- Import `DEFAULT_MAX_CONTEXT_LINES` from `.config`
- After getting the diff, read file contents:

```python
# After diff truncation, before building provider
max_context_raw = config.get("review", "max_context_lines")
max_context = int(max_context_raw) if max_context_raw else DEFAULT_MAX_CONTEXT_LINES
file_contents = {}
try:
    file_contents = get_staged_file_contents(extensions=extensions, max_lines=max_context)
except GitError:
    pass  # Fall back to diff-only
```

- Pass to reviewer: `result = reviewer.review_diff(diff, custom_rules=custom_rules, file_contents=file_contents)`

- [ ] **Step 5b: Update cli.py `pre_push_cmd()` to pass file context**

In `pre_push_cmd()`, after collecting diffs, read file contents for the last commit:

```python
# After collecting all_diff, before building provider
file_contents = {}
if local_sha and local_sha != _ZERO_SHA:
    try:
        file_contents = get_commit_file_contents(local_sha, extensions=extensions, max_lines=max_context)
    except GitError:
        pass
```

- Pass to reviewer: `result = reviewer.review_diff(all_diff, custom_rules=custom_rules, file_contents=file_contents)`

- [ ] **Step 6: Write CLI integration test**

```python
# tests/test_cli.py — add to existing file

class TestHybridContext:
    """Tests for hybrid review context in CLI."""

    def test_review_passes_file_contents_to_reviewer(self, runner):
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff content"), \
             patch("ai_code_review.cli.get_staged_file_contents", return_value={"main.c": "code"}) as mock_contents, \
             patch("ai_code_review.cli._build_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.review_code.return_value = ReviewResult()
            mock_provider_fn.return_value = mock_provider

            result = runner.invoke(main, [])
            mock_contents.assert_called_once()

    def test_review_falls_back_on_git_error(self, runner):
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff"), \
             patch("ai_code_review.cli.get_staged_file_contents", side_effect=GitError("fail")), \
             patch("ai_code_review.cli._build_provider") as mock_provider_fn:
            mock_provider = MagicMock()
            mock_provider.review_code.return_value = ReviewResult()
            mock_provider_fn.return_value = mock_provider

            result = runner.invoke(main, [])
            # Should still succeed with diff-only
            assert result.exit_code == 0
```

- [ ] **Step 7: Run all tests**

Run: `source .venv/bin/activate && pytest tests/test_reviewer.py::TestReviewDiffWithContext tests/test_cli.py::TestHybridContext -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/ai_code_review/reviewer.py src/ai_code_review/cli.py src/ai_code_review/config.py tests/test_reviewer.py tests/test_cli.py
git commit -m "feat: thread file context through reviewer and CLI for hybrid review"
```

---

## Chunk 2: Part 2 — Interactive Commit Message Template

### Task 4: Update commit message format validation

**Files:**
- Modify: `src/ai_code_review/commit_check.py`
- Modify: `tests/test_commit_check.py`

**Dependencies:** None (independent, can run in parallel with Part 1)

- [ ] **Step 1: Write failing tests for new format**

```python
# tests/test_commit_check.py — update existing tests

class TestNewCommitMessageFormat:
    """Tests for [UPDATE]?[CATEGORY][COMPONENT] format."""

    def test_valid_basic(self):
        result = check_commit_message("[BSP][CAMERA] fix null pointer crash")
        assert result.valid is True

    def test_valid_with_update(self):
        result = check_commit_message("[UPDATE][AP][NAL] update installation manager")
        assert result.valid is True

    def test_valid_cp_category(self):
        result = check_commit_message("[CP][AUDIO] add mixer path for headphone")
        assert result.valid is True

    def test_invalid_lowercase_component(self):
        result = check_commit_message("[BSP][camera] fix crash")
        assert result.valid is False

    def test_invalid_old_format(self):
        result = check_commit_message("[BSP-456] fix crash")
        assert result.valid is False

    def test_invalid_missing_component(self):
        result = check_commit_message("[BSP] fix crash")
        assert result.valid is False

    def test_invalid_wrong_category(self):
        result = check_commit_message("[QA][CAMERA] fix crash")
        assert result.valid is False

    def test_invalid_update_wrong_position(self):
        result = check_commit_message("[BSP][UPDATE][CAMERA] fix crash")
        assert result.valid is False

    def test_invalid_empty(self):
        result = check_commit_message("")
        assert result.valid is False

    def test_invalid_no_description(self):
        result = check_commit_message("[BSP][CAMERA]")
        assert result.valid is False

    def test_valid_update_lowercase_rejected(self):
        result = check_commit_message("[update][BSP][CAMERA] fix crash")
        assert result.valid is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_commit_check.py::TestNewCommitMessageFormat -v`
Expected: FAIL — old regex doesn't match new format

- [ ] **Step 3: Update commit_check.py**

```python
# src/ai_code_review/commit_check.py — full file rewrite
from __future__ import annotations

import re
from dataclasses import dataclass

_COMMIT_MSG_PATTERN = re.compile(
    r"^(\[UPDATE\])?\[(BSP|CP|AP)\]\[[A-Z]+\] .+"
)

_FORMAT_HINT = (
    "Commit message must match: [CATEGORY][COMPONENT] description\n"
    "  Categories: BSP, CP, AP\n"
    "  Component must be UPPERCASE\n"
    "  Optional [UPDATE] prefix for follow-up commits\n"
    "  Examples:\n"
    "    [BSP][CAMERA] fix null pointer crash\n"
    "    [UPDATE][AP][NAL] update installation manager"
)


@dataclass(frozen=True)
class CommitCheckResult:
    valid: bool
    error: str | None = None


def check_commit_message(message: str) -> CommitCheckResult:
    message = message.strip()
    if not message:
        return CommitCheckResult(valid=False, error="Empty commit message.")
    # Take first line only for format check
    first_line = message.split("\n")[0].strip()
    if not _COMMIT_MSG_PATTERN.match(first_line):
        return CommitCheckResult(valid=False, error=_FORMAT_HINT)
    return CommitCheckResult(valid=True)
```

- [ ] **Step 4: Remove old format tests**

Remove existing tests that validate the old `[PROJECT-NUMBER]` format from `tests/test_commit_check.py` (class names like `TestCommitCheckValid`, `TestCommitCheckInvalid`, etc.). Also update any tests in `tests/test_cli.py` that construct commit messages in `[BSP-456]` format — change them to use `[BSP][CAMERA]` format. Keep only `TestNewCommitMessageFormat`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_commit_check.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/ai_code_review/commit_check.py tests/test_commit_check.py
git commit -m "feat: update commit message format to [CATEGORY][COMPONENT]"
```

---

### Task 5: Create commit_template.py — template definitions and Q&A flow

**Files:**
- Create: `src/ai_code_review/commit_template.py`
- Test: `tests/test_commit_template.py`

**Dependencies:** None (independent module)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_commit_template.py — new file

from unittest.mock import patch, MagicMock
import pytest

from ai_code_review.commit_template import (
    CommitType,
    build_commit_message,
    run_interactive_qa,
    CATEGORIES,
)


class TestBuildCommitMessage:
    """Tests for assembling commit message from structured fields."""

    def test_feature_message(self):
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="CAMERA",
            summary="add preview frame rate control",
            commit_type=CommitType.FEATURE,
            impact_projects="LINUX/kernel/drivers/media/",
            description="Add configurable frame rate for camera preview",
            test="1. Preview at 30fps OK\n2. Preview at 60fps OK",
            modified_files=["drivers/media/camera.c"],
        )
        assert msg.startswith("[BSP][CAMERA] add preview frame rate control")
        assert "[IMPACT PROJECTS]" in msg
        assert "LINUX/kernel/drivers/media/" in msg
        assert "[DESCRIPTION]" in msg
        assert "Add configurable frame rate" in msg
        assert "modified:" in msg
        assert "drivers/media/camera.c" in msg
        assert "[TEST]" in msg

    def test_bugfix_message(self):
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="CAMERA",
            summary="fix boot hang caused by reset GPIO",
            commit_type=CommitType.BUGFIX,
            impact_projects="LINUX/kernel/",
            description=None,
            test="1. Boot OK",
            modified_files=["arch/arm64/boot/dts/camera.dtsi"],
            bug_id="JIRA-12345",
            symptom="EVT2 hangs at boot",
            root_cause="GPIO pin held high",
            solution="Set gpio-pin to 0",
        )
        assert msg.startswith("[BSP][CAMERA] fix boot hang")
        assert "BUG-ID: JIRA-12345" in msg
        assert "SYMPTOM: EVT2 hangs at boot" in msg
        assert "ROOT CAUSE: GPIO pin held high" in msg
        assert "SOLUTION: Set gpio-pin to 0" in msg

    def test_update_prefix(self):
        msg = build_commit_message(
            is_update=True,
            category="AP",
            component="NAL",
            summary="update installation manager",
            commit_type=CommitType.FEATURE,
            impact_projects="LINUX/android/",
            description="Update app",
            test="Build OK",
            modified_files=["Android.mk"],
        )
        assert msg.startswith("[UPDATE][AP][NAL]")

    def test_no_update_prefix(self):
        msg = build_commit_message(
            is_update=False,
            category="CP",
            component="AUDIO",
            summary="add mixer path",
            commit_type=CommitType.FEATURE,
            impact_projects="LINUX/",
            description="Add path",
            test="Test OK",
            modified_files=[],
        )
        assert msg.startswith("[CP][AUDIO]")
        assert "[UPDATE]" not in msg


class TestCategories:
    def test_valid_categories(self):
        assert "BSP" in CATEGORIES
        assert "CP" in CATEGORIES
        assert "AP" in CATEGORIES
        assert len(CATEGORIES) == 3


class TestRunInteractiveQa:
    """Tests for interactive Q&A flow using click.prompt mocks."""

    def test_feature_flow(self):
        inputs = iter(["i", "f", "BSP", "CAMERA", "add feature X",
                       "LINUX/kernel/", "Added feature X to camera", "Build OK"])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=["camera.c"],
                default_category=None,
                components=["CAMERA", "AUDIO"],
            )
        assert result["is_update"] is False
        assert result["commit_type"] == CommitType.FEATURE
        assert result["category"] == "BSP"
        assert result["component"] == "CAMERA"

    def test_bugfix_flow(self):
        inputs = iter(["i", "b", "BSP", "CAMERA", "fix crash",
                       "LINUX/kernel/", "JIRA-123", "crash on boot",
                       "null pointer", "add null check", "Boot OK"])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=["camera.c"],
                default_category=None,
                components=["CAMERA", "AUDIO"],
            )
        assert result["commit_type"] == CommitType.BUGFIX
        assert result["bug_id"] == "JIRA-123"
        assert result["symptom"] == "crash on boot"

    def test_update_flow(self):
        inputs = iter(["u", "f", "AP", "NAL", "update app",
                       "LINUX/android/", "Update app version", "Build OK"])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=["app.apk"],
                default_category=None,
                components=["NAL"],
            )
        assert result["is_update"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_commit_template.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_code_review.commit_template'`

- [ ] **Step 3: Implement commit_template.py**

```python
# src/ai_code_review/commit_template.py
from __future__ import annotations

from enum import Enum

import click


class CommitType(Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"


CATEGORIES = ["BSP", "CP", "AP"]

DEFAULT_COMPONENTS = [
    "CAMERA", "AUDIO", "DISPLAY", "SENSOR",
    "POWER", "THERMAL", "MEMORY", "STORAGE", "NAL",
]


def build_commit_message(
    *,
    is_update: bool,
    category: str,
    component: str,
    summary: str,
    commit_type: CommitType,
    impact_projects: str,
    description: str | None,
    test: str,
    modified_files: list[str],
    bug_id: str | None = None,
    symptom: str | None = None,
    root_cause: str | None = None,
    solution: str | None = None,
) -> str:
    """Assemble a structured commit message from fields."""
    # Title
    prefix = "[UPDATE]" if is_update else ""
    title = f"{prefix}[{category}][{component}] {summary}"

    # Body
    parts = [title, ""]

    # [IMPACT PROJECTS]
    parts.append("[IMPACT PROJECTS]")
    parts.append(impact_projects)
    parts.append("")

    # [DESCRIPTION]
    parts.append("[DESCRIPTION]")
    if commit_type == CommitType.BUGFIX:
        if bug_id:
            parts.append(f"BUG-ID: {bug_id}")
        if symptom:
            parts.append(f"SYMPTOM: {symptom}")
        if root_cause:
            parts.append(f"ROOT CAUSE: {root_cause}")
        if solution:
            parts.append(f"SOLUTION: {solution}")
    else:
        if description:
            parts.append(description)
    parts.append("")

    # modified:
    parts.append("modified:")
    for f in modified_files:
        parts.append(f)
    parts.append("")

    # [TEST]
    parts.append("[TEST]")
    parts.append(test)

    return "\n".join(parts)


def run_interactive_qa(
    *,
    modified_files: list[str],
    default_category: str | None = None,
    components: list[str] | None = None,
) -> dict:
    """Run interactive Q&A and return structured fields."""
    if components is None:
        components = DEFAULT_COMPONENTS

    component_hint = " / ".join(components) + " / (custom)"

    # Init or Update
    is_update_raw = click.prompt(
        "New or update? [i]nit / [u]pdate",
        type=click.Choice(["i", "u"], case_sensitive=False),
    )
    is_update = is_update_raw.lower() == "u"

    # Type
    type_raw = click.prompt(
        "Type? [f]eature / [b]ugfix",
        type=click.Choice(["f", "b"], case_sensitive=False),
    )
    commit_type = CommitType.FEATURE if type_raw.lower() == "f" else CommitType.BUGFIX

    # Category
    if default_category and default_category in CATEGORIES:
        category = click.prompt(
            f"Category? {' / '.join(CATEGORIES)}",
            default=default_category,
        )
    else:
        category = click.prompt(
            f"Category? {' / '.join(CATEGORIES)}",
            type=click.Choice(CATEGORIES, case_sensitive=False),
        )
    category = category.upper()

    # Component
    component = click.prompt(f"Component? {component_hint}")
    component = component.upper()

    # Summary
    summary = click.prompt("Summary?")

    # Impact Projects
    impact_projects = click.prompt("Impact projects?")

    # Type-specific fields
    bug_id = None
    symptom = None
    root_cause = None
    solution = None
    description = None

    if commit_type == CommitType.BUGFIX:
        bug_id = click.prompt("Bug ID?")
        symptom = click.prompt("Symptom?")
        root_cause = click.prompt("Root cause?")
        solution = click.prompt("Solution?")
    else:
        description = click.prompt("Description?")

    # Test
    test = click.prompt("Test?")

    return {
        "is_update": is_update,
        "commit_type": commit_type,
        "category": category,
        "component": component,
        "summary": summary,
        "impact_projects": impact_projects,
        "description": description,
        "test": test,
        "modified_files": modified_files,
        "bug_id": bug_id,
        "symptom": symptom,
        "root_cause": root_cause,
        "solution": solution,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_commit_template.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/commit_template.py tests/test_commit_template.py
git commit -m "feat: add commit_template module with Q&A flow and message assembly"
```

---

### Task 6: Add commit message polishing prompt

**Files:**
- Modify: `src/ai_code_review/prompts.py`
- Modify: `src/ai_code_review/reviewer.py`
- Modify: `src/ai_code_review/llm/base.py`
- Test: `tests/test_prompts.py`
- Test: `tests/test_reviewer.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_prompts.py — add

class TestCommitPolishPrompt:
    def test_includes_user_fields_and_diff(self):
        from ai_code_review.prompts import get_commit_polish_prompt
        prompt = get_commit_polish_prompt(
            summary="fix crash on boot",
            description="null pointer in camera init",
            diff="- ptr = NULL;\n+ ptr = malloc(size);",
        )
        assert "fix crash on boot" in prompt
        assert "null pointer in camera init" in prompt
        assert "ptr = malloc(size)" in prompt
        assert "grammar" in prompt.lower() or "polish" in prompt.lower()


# tests/test_reviewer.py — add

class TestComposeCommitMessage:
    def test_delegates_to_provider(self):
        provider = MagicMock()
        provider.polish_commit_msg.return_value = "polished summary"
        reviewer = Reviewer(provider=provider)
        result = reviewer.polish_commit_message(
            summary="fix crash",
            description="null ptr",
            diff="diff content",
        )
        assert result == "polished summary"
        provider.polish_commit_msg.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestCommitPolishPrompt tests/test_reviewer.py::TestComposeCommitMessage -v`
Expected: FAIL

- [ ] **Step 3: Add polishing prompt to prompts.py**

```python
# src/ai_code_review/prompts.py — add

_COMMIT_POLISH_PROMPT = """\
You are a technical writing assistant for Android BSP commit messages.

Given the user's summary and description, plus the git diff:
1. Fix English grammar and spelling
2. Make the summary more precise based on the actual code changes
3. Enrich the description with specific details from the diff (variable names, function names, file paths)
4. Keep the summary under 72 characters
5. Return ONLY the polished text in this exact format:

SUMMARY: <polished summary>
DESCRIPTION: <polished description>

User summary: {summary}
User description: {description}

Diff:
{diff}"""


def get_commit_polish_prompt(summary: str, description: str, diff: str) -> str:
    return _COMMIT_POLISH_PROMPT.format(summary=summary, description=description, diff=diff)
```

- [ ] **Step 4: Add `polish_commit_msg()` to LLMProvider ABC and implementations**

In `src/ai_code_review/llm/base.py`, add abstract method:
```python
@abstractmethod
def polish_commit_msg(self, summary: str, description: str, diff: str) -> str: ...
```

In each provider (ollama.py, openai.py, enterprise.py), add:
```python
def polish_commit_msg(self, summary: str, description: str, diff: str) -> str:
    from ..prompts import get_commit_polish_prompt
    prompt = get_commit_polish_prompt(summary, description, diff)
    return self._chat(prompt).strip()
```

- [ ] **Step 5: Add `polish_commit_message()` to Reviewer**

```python
# src/ai_code_review/reviewer.py — add method
def polish_commit_message(self, summary: str, description: str, diff: str) -> str:
    return self._provider.polish_commit_msg(summary, description, diff)
```

- [ ] **Step 6: Add provider-level tests for `polish_commit_msg()`**

```python
# tests/test_llm/test_ollama.py — add
class TestOllamaPolishCommitMsg:
    @respx.mock
    def test_polish_commit_msg_returns_response(self):
        respx.post("http://localhost:11434/api/chat").mock(
            return_value=httpx.Response(200, json={
                "message": {"content": "SUMMARY: polished\nDESCRIPTION: polished desc"}
            })
        )
        provider = OllamaProvider(base_url="http://localhost:11434", model="test")
        result = provider.polish_commit_msg("fix crash", "null ptr", "diff")
        assert "polished" in result

# tests/test_llm/test_openai.py — add
class TestOpenAIPolishCommitMsg:
    def test_polish_commit_msg_returns_response(self):
        with patch("ai_code_review.llm.openai.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "SUMMARY: polished"
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            provider = OpenAIProvider(api_key="test-key", model="gpt-4o")
            result = provider.polish_commit_msg("fix", "desc", "diff")
            assert "polished" in result

# tests/test_llm/test_enterprise.py — add (similar to ollama pattern with respx)
```

- [ ] **Step 7: Run all tests**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestCommitPolishPrompt tests/test_reviewer.py::TestComposeCommitMessage tests/test_llm/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/ai_code_review/prompts.py src/ai_code_review/reviewer.py src/ai_code_review/llm/base.py src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py tests/test_prompts.py tests/test_reviewer.py tests/test_llm/
git commit -m "feat: add commit message polishing prompt and provider method"
```

---

### Task 7: Update `_COMMIT_IMPROVE_PROMPT` for new format

**Files:**
- Modify: `src/ai_code_review/prompts.py`
- Modify: `tests/test_prompts.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Write failing test**

```python
# tests/test_prompts.py — update existing TestCommitImprovePrompt or add

class TestCommitImprovePromptNewFormat:
    def test_references_new_prefix_format(self):
        from ai_code_review.prompts import get_commit_improve_prompt
        prompt = get_commit_improve_prompt(
            "[BSP][CAMERA] fix crash", "diff content"
        )
        assert "prefix tags" in prompt or "[UPDATE][BSP][CAMERA]" in prompt
        assert "[PROJECT-NUMBER]" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestCommitImprovePromptNewFormat -v`
Expected: FAIL — old prompt still references `[PROJECT-NUMBER]`

- [ ] **Step 3: Update `_COMMIT_IMPROVE_PROMPT`**

```python
_COMMIT_IMPROVE_PROMPT = """\
You are a technical writing assistant. Given the original commit message and the git diff:
1. Fix English grammar errors
2. Make the description accurately reflect the code changes
3. Keep the first line under 72 characters total
4. Preserve the prefix tags exactly as-is (e.g., [UPDATE][BSP][CAMERA])

Respond with only the improved commit message. No explanation, no quotes.

Original: {message}

Diff:
{diff}"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_prompts.py::TestCommitImprovePromptNewFormat -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/prompts.py tests/test_prompts.py
git commit -m "feat: update commit improve prompt for new [CATEGORY][COMPONENT] format"
```

---

### Task 8: Rewire `generate_commit_msg_cmd()` to use interactive Q&A

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Test: `tests/test_cli.py`

**Dependencies:** Task 4, Task 5, Task 6

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py — add

class TestInteractiveCommitMsg:
    """Tests for interactive commit message generation."""

    def test_interactive_qa_triggers_on_tty(self, runner):
        """When stdin is a TTY, interactive Q&A runs."""
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff"), \
             patch("ai_code_review.cli.sys") as mock_sys, \
             patch("ai_code_review.cli.run_interactive_qa") as mock_qa, \
             patch("ai_code_review.cli.build_commit_message", return_value="[BSP][CAM] msg"), \
             patch("ai_code_review.cli._build_provider"):
            mock_sys.stdin.isatty.return_value = True
            mock_qa.return_value = {
                "is_update": False, "category": "BSP", "component": "CAMERA",
                "summary": "fix crash", "commit_type": CommitType.FEATURE,
                "impact_projects": "LINUX/", "description": "Fix it",
                "test": "OK", "modified_files": ["a.c"],
                "bug_id": None, "symptom": None, "root_cause": None, "solution": None,
            }

            result = runner.invoke(main, ["generate-commit-msg", "/tmp/msg"])
            mock_qa.assert_called_once()

    def test_falls_back_to_auto_generate_when_not_tty(self, runner, tmp_path):
        """When stdin is not a TTY, use old auto-generate behavior."""
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff"), \
             patch("ai_code_review.cli.sys") as mock_sys, \
             patch("ai_code_review.cli._build_provider") as mock_provider_fn:
            mock_sys.stdin.isatty.return_value = False
            mock_provider = MagicMock()
            mock_provider.generate_commit_msg.return_value = "auto generated msg"
            mock_provider_fn.return_value = mock_provider

            msg_file = tmp_path / "COMMIT_EDITMSG"
            msg_file.write_text("")
            result = runner.invoke(main, ["generate-commit-msg", str(msg_file)])
            # Should use auto-generate, not interactive
            mock_provider.generate_commit_msg.assert_called()

    def test_auto_accept_skips_qa(self, runner, tmp_path):
        """--auto-accept or AI_REVIEW_AUTO_ACCEPT=1 skips Q&A, uses auto-generate."""
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff"), \
             patch("ai_code_review.cli._build_provider") as mock_provider_fn, \
             patch.dict("os.environ", {"AI_REVIEW_AUTO_ACCEPT": "1"}):
            mock_provider = MagicMock()
            mock_provider.generate_commit_msg.return_value = "auto msg"
            mock_provider_fn.return_value = mock_provider

            msg_file = tmp_path / "COMMIT_EDITMSG"
            msg_file.write_text("")
            result = runner.invoke(main, ["generate-commit-msg", str(msg_file)])
            mock_provider.generate_commit_msg.assert_called()

    def test_skip_for_merge_source(self, runner):
        """Skip Q&A for merge commits."""
        result = runner.invoke(main, ["generate-commit-msg", "/tmp/msg", "merge"])
        assert result.exit_code == 0

    def test_message_source_no_longer_skipped(self, runner):
        """source='message' (-m flag) should NOT skip — triggers Q&A."""
        with patch("ai_code_review.cli.get_staged_diff", return_value="diff"), \
             patch("ai_code_review.cli.sys") as mock_sys, \
             patch("ai_code_review.cli.run_interactive_qa") as mock_qa, \
             patch("ai_code_review.cli.build_commit_message", return_value="[BSP][CAM] msg"), \
             patch("ai_code_review.cli._build_provider"):
            mock_sys.stdin.isatty.return_value = True
            mock_qa.return_value = {
                "is_update": False, "category": "BSP", "component": "CAMERA",
                "summary": "fix", "commit_type": CommitType.FEATURE,
                "impact_projects": "L/", "description": "D",
                "test": "T", "modified_files": ["a.c"],
                "bug_id": None, "symptom": None, "root_cause": None, "solution": None,
            }

            result = runner.invoke(main, ["generate-commit-msg", "/tmp/msg", "message"])
            mock_qa.assert_called_once()


class TestExtractModifiedFiles:
    """Tests for _extract_modified_files helper."""

    def test_extracts_file_paths(self):
        from ai_code_review.cli import _extract_modified_files
        diff = "--- a/old.c\n+++ b/main.c\n@@ -1 +1 @@\n-old\n+new\n--- a/utils.h\n+++ b/utils.h\n"
        files = _extract_modified_files(diff)
        assert "main.c" in files
        assert "utils.h" in files

    def test_handles_new_file(self):
        from ai_code_review.cli import _extract_modified_files
        diff = "--- /dev/null\n+++ b/new_file.c\n"
        files = _extract_modified_files(diff)
        assert "new_file.c" in files

    def test_handles_deleted_file(self):
        from ai_code_review.cli import _extract_modified_files
        diff = "--- a/removed.c\n+++ /dev/null\n"
        files = _extract_modified_files(diff)
        # /dev/null should not appear as a file
        assert "/dev/null" not in files

    def test_empty_diff(self):
        from ai_code_review.cli import _extract_modified_files
        assert _extract_modified_files("") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_cli.py::TestInteractiveCommitMsg -v`
Expected: FAIL

- [ ] **Step 3: Rewrite `generate_commit_msg_cmd()`**

Update `src/ai_code_review/cli.py`:

```python
import sys
from .commit_template import CommitType, build_commit_message, run_interactive_qa

@main.command("generate-commit-msg")
@click.argument("message_file")
@click.argument("source", required=False, default="")
@click.argument("sha", required=False, default="")
@click.pass_context
def generate_commit_msg_cmd(ctx, message_file, source, sha):
    """Generate commit message via interactive Q&A or auto-generate."""
    # Skip for merge, squash, amend (but NOT "message" — we want Q&A even with -m)
    if source in ("merge", "squash", "commit"):
        return

    graceful = ctx.obj.get("graceful", False) if ctx.obj else False

    config = Config()

    ext_raw = config.get("review", "include_extensions")
    if ext_raw is None:
        ext_raw = DEFAULT_INCLUDE_EXTENSIONS
    extensions = [e.strip() for e in ext_raw.split(",") if e.strip()] if ext_raw else None

    try:
        diff = get_staged_diff(extensions=extensions)
    except GitError:
        return
    if not diff:
        return

    # Extract modified file list from diff
    modified_files = _extract_modified_files(diff)

    # Auto-accept mode skips Q&A (for non-interactive use)
    auto_accept = os.environ.get("AI_REVIEW_AUTO_ACCEPT") == "1"

    # Interactive Q&A if TTY available and not auto-accept
    if sys.stdin.isatty() and not auto_accept:
        default_category = config.get("commit", "default_category")
        components_raw = config.get("commit", "components")
        components = [c.strip() for c in components_raw.split(",")] if components_raw else None

        try:
            fields = run_interactive_qa(
                modified_files=modified_files,
                default_category=default_category,
                components=components,
            )
        except (EOFError, KeyboardInterrupt):
            return

        # Optional: AI polishing
        try:
            cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
            cli_model = ctx.obj.get("cli_model") if ctx.obj else None
            provider = _build_provider(config, cli_provider, cli_model)
            reviewer = Reviewer(provider=provider)
            polished = reviewer.polish_commit_message(
                summary=fields["summary"],
                description=fields.get("description") or fields.get("symptom") or "",
                diff=diff,
            )
            # Parse polished output
            if "SUMMARY:" in polished:
                for line in polished.split("\n"):
                    if line.startswith("SUMMARY:"):
                        fields["summary"] = line[len("SUMMARY:"):].strip()
                    elif line.startswith("DESCRIPTION:"):
                        if fields["commit_type"] == CommitType.FEATURE:
                            fields["description"] = line[len("DESCRIPTION:"):].strip()
        except (ProviderNotConfiguredError, ProviderError) as e:
            if graceful:
                console.print(f"[yellow]Warning: AI polish skipped — {rich_escape(str(e))}[/]")

        message = build_commit_message(**fields)

        # Show preview
        console.print(f"\n[dim]---[/]")
        console.print(message)
        console.print(f"[dim]---[/]\n")

        choice = click.prompt(
            "[A]ccept / [E]dit / [S]kip",
            type=click.Choice(["a", "e", "s"], case_sensitive=False),
            default="a",
        )
        if choice == "a":
            Path(message_file).write_text(message + "\n")
            console.print("[green]Commit message written.[/]")
        elif choice == "e":
            edited = click.edit(message)
            if edited:
                Path(message_file).write_text(edited)
                console.print("[green]Commit message written.[/]")
        return

    # Non-TTY fallback: auto-generate (old behavior)
    try:
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config, cli_provider, cli_model)
    except (ProviderNotConfiguredError, ProviderError) as e:
        if graceful:
            console.print(f"[yellow]Warning: Cannot generate commit message — {rich_escape(str(e))}[/]")
        return

    reviewer = Reviewer(provider=provider)
    try:
        description = reviewer.generate_commit_message(diff)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: Commit message generation failed — {rich_escape(str(e))}[/]")
        return

    if not description:
        return

    default_category = config.get("commit", "default_category")
    if default_category:
        message = f"[{default_category}][MISC] {description}"
    else:
        message = description

    Path(message_file).write_text(message + "\n")
    console.print(f"[green]Generated: {rich_escape(message)}[/]")


def _extract_modified_files(diff: str) -> list[str]:
    """Extract file paths from diff output."""
    files = []
    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            files.append(line[6:])
        elif line.startswith("+++ ") and "/dev/null" not in line:
            files.append(line[4:])
    return files
```

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && pytest tests/test_cli.py::TestInteractiveCommitMsg -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `source .venv/bin/activate && pytest -v`
Expected: All tests PASS (fix any regressions from old `generate_commit_msg_cmd` tests)

- [ ] **Step 6: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: rewire generate-commit-msg to interactive Q&A with non-TTY fallback"
```

---

### Task 9: Update config for deprecation warning and new keys

**Files:**
- Modify: `src/ai_code_review/config.py`
- Test: `tests/test_config.py`

**Dependencies:** None (independent)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py — add

class TestDeprecationWarning:
    def test_warns_on_old_project_id(self, tmp_path, capsys):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text('[commit]\nproject_id = "BSP-456"\n')

        config = Config(config_dir=config_dir)
        warning = config.check_deprecated_keys()
        assert "project_id" in warning
        assert "default_category" in warning

    def test_no_warning_without_old_key(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text('[commit]\ndefault_category = "BSP"\n')

        config = Config(config_dir=config_dir)
        warning = config.check_deprecated_keys()
        assert warning is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_config.py::TestDeprecationWarning -v`
Expected: FAIL — `check_deprecated_keys` doesn't exist

- [ ] **Step 3: Implement**

```python
# src/ai_code_review/config.py — add method to Config class

def check_deprecated_keys(self) -> str | None:
    """Check for deprecated config keys and return warning message."""
    project_id = self.get("commit", "project_id")
    if project_id:
        return (
            f"Warning: 'commit.project_id' is deprecated. "
            f"Use 'commit.default_category' instead.\n"
            f"  Run: ai-review config set commit default_category {project_id}\n"
            f"  Then: ai-review config set commit project_id \"\""
        )
    return None
```

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && pytest tests/test_config.py::TestDeprecationWarning -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/config.py tests/test_config.py
git commit -m "feat: add deprecation warning for commit.project_id config"
```

---

### Task 10: Wire deprecation warning into CLI

**Files:**
- Modify: `src/ai_code_review/cli.py`
- Test: `tests/test_cli.py`

**Dependencies:** Task 9

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py — add

class TestDeprecationWarningCli:
    def test_shows_deprecation_warning(self, runner, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[commit]\nproject_id = "BSP-456"\n[provider]\ndefault = "ollama"\n')

        with patch("ai_code_review.cli.Config") as MockConfig:
            mock_config = MagicMock()
            mock_config.check_deprecated_keys.return_value = "Warning: deprecated"
            mock_config.get.return_value = None
            mock_config.resolve_provider.return_value = None
            MockConfig.return_value = mock_config

            result = runner.invoke(main, [])
            assert "deprecated" in result.output.lower() or mock_config.check_deprecated_keys.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_cli.py::TestDeprecationWarningCli -v`
Expected: FAIL

- [ ] **Step 3: Add deprecation check to `_review()` and `generate_commit_msg_cmd()`**

In `_review()` and `generate_commit_msg_cmd()`, after creating Config:
```python
config = Config()
deprecation = config.check_deprecated_keys()
if deprecation:
    console.print(f"[yellow]{rich_escape(deprecation)}[/]")
```

- [ ] **Step 4: Run test**

Run: `source .venv/bin/activate && pytest tests/test_cli.py::TestDeprecationWarningCli -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: show deprecation warning for commit.project_id in CLI"
```

---

### Task 11: Run full test suite and fix regressions

**Files:**
- Potentially modify: any file with failing tests

**Dependencies:** All previous tasks

- [ ] **Step 1: Run full test suite**

Run: `source .venv/bin/activate && pytest -v`

- [ ] **Step 2: Fix any regressions**

Common expected regressions:
- Old `TestGenerateCommitMsgCommand` tests may fail due to changed behavior (update or remove)
- Old `test_commit_check.py` tests for `[PROJECT-NUMBER]` format need removal
- Import changes may break existing mocks

- [ ] **Step 3: Verify all tests pass**

Run: `source .venv/bin/activate && pytest -v`
Expected: All PASS

- [ ] **Step 4: Commit fixes**

```bash
git add -u
git commit -m "fix: update existing tests for new commit format and interactive Q&A"
```

---

## Chunk 3: Documentation and Cleanup

### Task 12: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/SOP.md`

**Dependencies:** Task 11

- [ ] **Step 1: Update CLAUDE.md**

- Update commit message format description from `[PROJECT-NUMBER]` to `[CATEGORY][COMPONENT]`
- Add `commit_template.py` to architecture section
- Add `review.max_context_lines` to key patterns
- Update `generate-commit-msg` description to mention interactive Q&A
- Update test count

- [ ] **Step 2: Update README.md**

- Update commit message format examples
- Add `commit.default_category` and `commit.components` to config table
- Remove `commit.project_id` (mark deprecated)
- Update Quick Start workflow to reflect interactive Q&A

- [ ] **Step 3: Update docs/SOP.md**

- Update commit message format section with new examples
- Update workflow diagram to show interactive Q&A step
- Update config reference with new keys
- Add migration note for `commit.project_id`

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/SOP.md
git commit -m "docs: update for new commit format and hybrid review context"
```

---

## Task Dependency Graph

```
Part 1 (Hybrid Context):        Part 2 (Commit Template):
  Task 1 ──┐                      Task 4 (regex) ────┐
  Task 2 ──┼── Task 3             Task 5 (template) ──┼── Task 8 (CLI rewire)
           │                      Task 6 (polish) ────┘        │
           │                      Task 7 (improve prompt)      │
           │                      Task 9 (config) ── Task 10   │
           │                                                   │
           └───────────────────── Task 11 (regressions) ───────┘
                                       │
                                  Task 12 (docs)
```

**Parallel execution opportunities:**
- Tasks 1, 2, 4, 5, 6, 7, 9 are all independent — can run in parallel
- Task 3 waits for 1+2
- Task 8 waits for 4+5+6
- Task 10 waits for 9
- Task 11 waits for all implementation tasks
- Task 12 waits for 11
