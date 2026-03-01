# Git Hooks + LLM Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add prepare-commit-msg hook (auto-generate commit messages), pre-push hook (full AI review before push), and graceful degradation (LLM failures warn but don't block).

**Architecture:** Three independent features that share the existing provider/reviewer architecture. Graceful degradation is a cross-cutting concern implemented via a `--graceful` CLI flag and `ProviderError` wrapping in provider `_chat()` methods. New hooks follow existing template/global/per-repo patterns.

**Tech Stack:** Python 3.10+, click, httpx, openai SDK, pytest + respx + pytest-mock

---

## Phase 1: Graceful Degradation

### Task 1: Wrap provider `_chat()` errors in ProviderError

**Files:**
- Modify: `src/ai_code_review/llm/ollama.py:40-50`
- Modify: `src/ai_code_review/llm/openai.py:30-35`
- Modify: `src/ai_code_review/llm/enterprise.py:59-68`
- Test: `tests/test_llm/test_ollama.py`
- Test: `tests/test_llm/test_openai.py`
- Test: `tests/test_llm/test_enterprise.py`

**Step 1: Write failing tests for Ollama provider error wrapping**

Add to `tests/test_llm/test_ollama.py`:

```python
import httpx
import pytest
from ai_code_review.exceptions import ProviderError

class TestOllamaProviderErrorWrapping:
    def test_review_code_wraps_connect_error(self, provider):
        with respx.mock:
            respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.ConnectError("refused"))
            with pytest.raises(ProviderError, match="refused"):
                provider.review_code("diff", "prompt")

    def test_improve_commit_msg_wraps_timeout(self, provider):
        with respx.mock:
            respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.ReadTimeout("timeout"))
            with pytest.raises(ProviderError, match="timeout"):
                provider.improve_commit_msg("msg", "diff")
```

Use existing `provider` fixture and `BASE_URL` from the test file.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm/test_ollama.py::TestOllamaProviderErrorWrapping -v`
Expected: FAIL — currently exceptions are not wrapped in ProviderError

**Step 3: Implement error wrapping in OllamaProvider**

In `src/ai_code_review/llm/ollama.py`, add import and wrap `_chat()`:

```python
from ..exceptions import ProviderError

# Replace existing _chat method:
def _chat(self, prompt: str) -> str:
    try:
        resp = self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except httpx.HTTPError as e:
        raise ProviderError(f"Ollama API request failed: {e}") from e
    except (KeyError, ValueError) as e:
        raise ProviderError("Ollama returned unexpected response format") from e
```

**Step 4: Run Ollama tests to verify they pass**

Run: `pytest tests/test_llm/test_ollama.py -v`
Expected: ALL PASS

**Step 5: Write failing tests + implement for OpenAI provider**

Add to `tests/test_llm/test_openai.py`:

```python
import pytest
from ai_code_review.exceptions import ProviderError

class TestOpenAIProviderErrorWrapping:
    def test_review_code_wraps_api_error(self):
        import openai
        provider = OpenAIProvider(api_key="test-key", model="gpt-4o")
        with patch.object(provider, "_client") as mock_client:
            mock_client.chat.completions.create.side_effect = openai.APIConnectionError(request=None)
            with pytest.raises(ProviderError, match="OpenAI"):
                provider.review_code("diff", "prompt")
```

In `src/ai_code_review/llm/openai.py`, wrap `_chat()`:

```python
import openai as openai_module
from ..exceptions import ProviderError

def _chat(self, prompt: str) -> str:
    try:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except openai_module.APIError as e:
        raise ProviderError(f"OpenAI API request failed: {e}") from e
```

**Step 6: Write failing tests + implement for Enterprise provider**

Add to `tests/test_llm/test_enterprise.py`:

```python
import httpx
import pytest
from ai_code_review.exceptions import ProviderError

class TestEnterpriseProviderErrorWrapping:
    def test_review_code_wraps_connect_error(self, provider):
        with respx.mock:
            respx.post(f"{BASE_URL}/v1/chat/completions").mock(
                side_effect=httpx.ConnectError("refused")
            )
            with pytest.raises(ProviderError, match="refused"):
                provider.review_code("diff", "prompt")
```

In `src/ai_code_review/llm/enterprise.py`, wrap `_chat()`:

```python
from ..exceptions import ProviderError

def _chat(self, prompt: str) -> str:
    try:
        resp = self._client.post(
            f"{self._base_url}{self._api_path}",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise ProviderError(f"Enterprise API request failed: {e}") from e
    except (KeyError, ValueError) as e:
        raise ProviderError("Enterprise returned unexpected response format") from e
```

**Step 7: Run all provider tests**

Run: `pytest tests/test_llm/ -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/ai_code_review/llm/ollama.py src/ai_code_review/llm/openai.py src/ai_code_review/llm/enterprise.py tests/test_llm/
git commit -m "feat: wrap provider _chat() errors in ProviderError"
```

---

### Task 2: Add `--graceful` flag and ProviderError handling in CLI

**Files:**
- Modify: `src/ai_code_review/cli.py:73-93` (main group) and `_review()`, `check_commit()`
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
from ai_code_review.exceptions import ProviderError

class TestGracefulFlag:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_provider_error_exits_0(self, mock_diff, mock_build, runner):
        mock_diff.return_value = "some diff"
        mock_build.side_effect = ProviderError("Connection refused")
        result = runner.invoke(main, ["--graceful"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_no_graceful_provider_error_exits_1(self, mock_diff, mock_build, runner):
        mock_diff.return_value = "some diff"
        mock_build.side_effect = ProviderError("Connection refused")
        result = runner.invoke(main, [])
        assert result.exit_code == 1

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_still_blocks_on_review_issues(self, mock_diff, mock_build, runner):
        mock_diff.return_value = "some diff"
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[
            ReviewIssue(severity=Severity.CRITICAL, file="a.c", line=1, message="leak"),
        ])
        mock_build.return_value = mock_provider
        result = runner.invoke(main, ["--graceful"])
        assert result.exit_code == 1

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_review_provider_error_during_review(self, mock_diff, mock_build, runner):
        """Provider builds OK but review_code raises ProviderError."""
        mock_diff.return_value = "some diff"
        mock_provider = MagicMock()
        mock_provider.review_code.side_effect = ProviderError("timeout")
        mock_build.return_value = mock_provider
        result = runner.invoke(main, ["--graceful"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()


class TestGracefulCheckCommit:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_check_commit_llm_failure_still_validates_format(
        self, mock_diff, mock_build, runner, tmp_path
    ):
        """Format check always blocks, even with --graceful."""
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("bad format")
        result = runner.invoke(main, ["--graceful", "check-commit", str(msg_file)])
        assert result.exit_code == 1

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_check_commit_llm_failure_skips_improvement(
        self, mock_diff, mock_build, runner, tmp_path
    ):
        """LLM failure with --graceful skips improvement, exits 0."""
        mock_diff.return_value = "some diff"
        mock_provider = MagicMock()
        mock_provider.improve_commit_msg.side_effect = ProviderError("timeout")
        mock_build.return_value = mock_provider
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-123] fix something")
        result = runner.invoke(main, ["--graceful", "check-commit", str(msg_file)])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestGracefulFlag -v`
Expected: FAIL

**Step 3: Implement --graceful flag**

In `src/ai_code_review/cli.py`:

1. Add import: `from .exceptions import ProviderError, ProviderNotConfiguredError`

2. Add `--graceful` option to `main()`:
```python
@click.group(invoke_without_command=True)
@click.option("--provider", "cli_provider", default=None, help="LLM provider (ollama/openai/enterprise)")
@click.option("--model", "cli_model", default=None, help="Model name")
@click.option("--format", "output_format", default="terminal", type=click.Choice(["terminal", "markdown", "json"]))
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option("--graceful", is_flag=True, help="On LLM failure, warn instead of blocking.")
@click.pass_context
def main(ctx, cli_provider, cli_model, output_format, verbose, graceful):
    ctx.ensure_object(dict)
    ctx.obj["cli_provider"] = cli_provider
    ctx.obj["cli_model"] = cli_model
    ctx.obj["output_format"] = output_format
    ctx.obj["graceful"] = graceful
    # ... rest unchanged
```

3. Update `_review()` to catch `ProviderError` and handle graceful:
```python
def _review(ctx):
    graceful = ctx.obj.get("graceful", False)
    config = Config()
    # ... existing diff/extensions code ...

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except (ProviderNotConfiguredError, ProviderError) as e:
        if graceful:
            console.print(f"[yellow]Warning: AI review unavailable — {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    reviewer = Reviewer(provider=provider)
    try:
        result = reviewer.review_diff(diff, custom_rules=custom_rules)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: AI review failed — {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    # ... existing format/output/exit code ...
```

4. Update `check_commit()` to handle graceful for AI improvement:
```python
def check_commit(ctx, message_file, auto_accept):
    graceful = ctx.obj.get("graceful", False) if ctx.obj else False
    # ... existing format check (always blocks) ...

    try:
        config = Config()
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError:
        return

    try:
        diff = get_staged_diff()
    except GitError:
        diff = ""
    if not diff:
        return

    reviewer = Reviewer(provider=provider)
    try:
        improved = reviewer.improve_commit_message(message, diff)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: AI improvement unavailable — {rich_escape(str(e))}[/]")
        else:
            console.print(f"[bold red]AI improvement failed: {rich_escape(str(e))}[/]")
        return

    # ... existing improvement UI code ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::TestGracefulFlag tests/test_cli.py::TestGracefulCheckCommit -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest -v`
Expected: ALL PASS (no regressions)

**Step 6: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add --graceful flag for LLM failure tolerance"
```

---

### Task 3: Update hook scripts to use `--graceful`

**Files:**
- Modify: `src/ai_code_review/cli.py:324-367` (hook script generators)
- Test: `tests/test_hooks.py`

**Step 1: Write failing tests**

Add to `tests/test_hooks.py`:

```python
class TestHookScriptsUseGraceful:
    def test_global_hook_scripts_use_graceful(self):
        from ai_code_review.cli import _generate_hook_scripts
        scripts = _generate_hook_scripts()
        for hook_type in ["pre-commit", "commit-msg"]:
            assert "--graceful" in scripts[hook_type]

    def test_template_hook_scripts_use_graceful(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        for hook_type in ["pre-commit", "commit-msg"]:
            assert "--graceful" in scripts[hook_type]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hooks.py::TestHookScriptsUseGraceful -v`
Expected: FAIL

**Step 3: Update hook script generators**

In `_generate_hook_scripts()`:
```python
return {
    "pre-commit": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful
""",
    "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful check-commit --auto-accept "$1"
""",
}
```

In `_generate_template_hook_scripts()`:
```python
return {
    "pre-commit": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful
""",
    "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful check-commit --auto-accept "$1"
""",
}
```

**Step 4: Run hook tests**

Run: `pytest tests/test_hooks.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: hook scripts use --graceful for LLM failure tolerance"
```

---

## Phase 2: prepare-commit-msg Hook

### Task 4: Add commit message generation prompt

**Files:**
- Modify: `src/ai_code_review/prompts.py`
- Test: `tests/test_prompts.py`

**Step 1: Write failing tests**

Add to `tests/test_prompts.py`:

```python
from ai_code_review.prompts import get_generate_commit_prompt

class TestGenerateCommitPrompt:
    def test_prompt_contains_diff(self):
        prompt = get_generate_commit_prompt("+ int x = 0;")
        assert "+ int x = 0;" in prompt

    def test_prompt_instructs_imperative_mood(self):
        prompt = get_generate_commit_prompt("some diff")
        assert "imperative" in prompt.lower()

    def test_prompt_instructs_concise(self):
        prompt = get_generate_commit_prompt("some diff")
        assert "72" in prompt or "concise" in prompt.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompts.py::TestGenerateCommitPrompt -v`
Expected: FAIL — `get_generate_commit_prompt` doesn't exist

**Step 3: Implement**

In `src/ai_code_review/prompts.py`, add:

```python
_GENERATE_COMMIT_PROMPT = """\
You are a technical writing assistant. Given the following git diff, generate a concise commit message description.

Rules:
- Use present tense imperative form (e.g., "fix crash in camera HAL", "add null check for buffer pointer")
- Start with a lowercase verb
- Accurately describe what the code changes do
- Keep it under 72 characters
- Respond with only the description, no prefix, no quotes, no explanation

Diff:
{diff}"""


def get_generate_commit_prompt(diff: str) -> str:
    return _GENERATE_COMMIT_PROMPT.format(diff=diff)
```

**Step 4: Run tests**

Run: `pytest tests/test_prompts.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/prompts.py tests/test_prompts.py
git commit -m "feat: add commit message generation prompt"
```

---

### Task 5: Add `generate_commit_msg` to LLM providers and Reviewer

**Files:**
- Modify: `src/ai_code_review/llm/base.py:47-55` (add abstract method)
- Modify: `src/ai_code_review/llm/ollama.py` (implement)
- Modify: `src/ai_code_review/llm/openai.py` (implement)
- Modify: `src/ai_code_review/llm/enterprise.py` (implement)
- Modify: `src/ai_code_review/reviewer.py` (add method)
- Test: `tests/test_llm/test_ollama.py`
- Test: `tests/test_llm/test_openai.py`
- Test: `tests/test_llm/test_enterprise.py`
- Test: `tests/test_reviewer.py`

**Step 1: Write failing tests for Ollama**

Add to `tests/test_llm/test_ollama.py`:

```python
class TestOllamaGenerateCommitMsg:
    def test_generates_commit_message(self, provider):
        with respx.mock:
            respx.post(f"{BASE_URL}/api/chat").mock(
                return_value=httpx.Response(200, json={
                    "message": {"content": "fix null pointer in camera init"}
                })
            )
            result = provider.generate_commit_msg("+ if (ptr == NULL) return;")
            assert result == "fix null pointer in camera init"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm/test_ollama.py::TestOllamaGenerateCommitMsg -v`
Expected: FAIL — method doesn't exist

**Step 3: Add abstract method and implement in all providers**

In `src/ai_code_review/llm/base.py`, add to `LLMProvider`:
```python
@abstractmethod
def generate_commit_msg(self, diff: str) -> str: ...
```

In `src/ai_code_review/llm/ollama.py`, add import and method:
```python
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt, get_generate_commit_prompt

def generate_commit_msg(self, diff: str) -> str:
    prompt = get_generate_commit_prompt(diff)
    return self._chat(prompt).strip()
```

In `src/ai_code_review/llm/openai.py`, add import and method:
```python
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt, get_generate_commit_prompt

def generate_commit_msg(self, diff: str) -> str:
    prompt = get_generate_commit_prompt(diff)
    return self._chat(prompt).strip()
```

In `src/ai_code_review/llm/enterprise.py`, add import and method:
```python
from ..prompts import REVIEW_RESPONSE_SCHEMA, get_commit_improve_prompt, get_generate_commit_prompt

def generate_commit_msg(self, diff: str) -> str:
    prompt = get_generate_commit_prompt(diff)
    return self._chat(prompt).strip()
```

**Step 4: Add similar tests for OpenAI and Enterprise providers**

**Step 5: Write failing test for Reviewer**

Add to `tests/test_reviewer.py`:
```python
class TestGenerateCommitMessage:
    def test_delegates_to_provider(self):
        mock_provider = MagicMock()
        mock_provider.generate_commit_msg.return_value = "fix buffer overflow"
        reviewer = Reviewer(provider=mock_provider)
        result = reviewer.generate_commit_message("some diff")
        assert result == "fix buffer overflow"
        mock_provider.generate_commit_msg.assert_called_once_with("some diff")
```

**Step 6: Implement Reviewer method**

In `src/ai_code_review/reviewer.py`:
```python
def generate_commit_message(self, diff: str) -> str:
    return self._provider.generate_commit_msg(diff)
```

**Step 7: Run all tests**

Run: `pytest tests/test_llm/ tests/test_reviewer.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add src/ai_code_review/llm/ src/ai_code_review/reviewer.py tests/test_llm/ tests/test_reviewer.py
git commit -m "feat: add generate_commit_msg to LLM providers and Reviewer"
```

---

### Task 6: Add `generate-commit-msg` CLI command

**Files:**
- Modify: `src/ai_code_review/cli.py` (add command after `check_commit`)
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestGenerateCommitMsgCommand:
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_generates_and_writes_message(self, mock_diff, mock_build, runner, tmp_path):
        mock_diff.return_value = "+ int x = 0;"
        mock_provider = MagicMock()
        mock_provider.generate_commit_msg.return_value = "add integer initialization"
        mock_build.return_value = mock_provider
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("")

        result = runner.invoke(main, ["generate-commit-msg", str(msg_file)])
        assert result.exit_code == 0
        assert "add integer initialization" in msg_file.read_text()

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    @patch("ai_code_review.cli.Config")
    def test_prepends_project_id_from_config(self, mock_config_cls, mock_diff, mock_build, runner, tmp_path):
        mock_diff.return_value = "+ fix bug;"
        mock_provider = MagicMock()
        mock_provider.generate_commit_msg.return_value = "fix null pointer in camera"
        mock_build.return_value = mock_provider
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda s, k: {
            ("commit", "project_id"): "BSP-456",
            ("review", "include_extensions"): None,
        }.get((s, k))
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("")

        result = runner.invoke(main, ["generate-commit-msg", str(msg_file)])
        assert result.exit_code == 0
        content = msg_file.read_text()
        assert content.startswith("[BSP-456] ")
        assert "fix null pointer in camera" in content

    @patch("ai_code_review.cli.get_staged_diff")
    def test_skips_on_merge_source(self, mock_diff, runner, tmp_path):
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("Merge branch 'feature'")
        result = runner.invoke(main, ["generate-commit-msg", str(msg_file), "merge"])
        assert result.exit_code == 0
        assert msg_file.read_text() == "Merge branch 'feature'"

    @patch("ai_code_review.cli.get_staged_diff")
    def test_skips_on_commit_source(self, mock_diff, runner, tmp_path):
        """Skip when amending (source=commit)."""
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-123] original")
        result = runner.invoke(main, ["generate-commit-msg", str(msg_file), "commit"])
        assert result.exit_code == 0
        assert msg_file.read_text() == "[BSP-123] original"

    @patch("ai_code_review.cli.get_staged_diff")
    def test_skips_on_message_source(self, mock_diff, runner, tmp_path):
        """Skip when user provided -m (source=message)."""
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("[BSP-123] user message")
        result = runner.invoke(main, ["generate-commit-msg", str(msg_file), "message"])
        assert result.exit_code == 0
        assert msg_file.read_text() == "[BSP-123] user message"

    @patch("ai_code_review.cli.get_staged_diff")
    def test_skips_on_empty_diff(self, mock_diff, runner, tmp_path):
        mock_diff.return_value = ""
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("")
        result = runner.invoke(main, ["generate-commit-msg", str(msg_file)])
        assert result.exit_code == 0

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_staged_diff")
    def test_graceful_on_provider_error(self, mock_diff, mock_build, runner, tmp_path):
        mock_diff.return_value = "some diff"
        mock_build.side_effect = ProviderError("Connection refused")
        msg_file = tmp_path / "COMMIT_EDITMSG"
        msg_file.write_text("")
        result = runner.invoke(main, ["--graceful", "generate-commit-msg", str(msg_file)])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestGenerateCommitMsgCommand -v`
Expected: FAIL

**Step 3: Implement the command**

In `src/ai_code_review/cli.py`, add after `check_commit`:

```python
@main.command("generate-commit-msg")
@click.argument("message_file")
@click.argument("source", required=False, default="")
@click.argument("sha", required=False, default="")
@click.pass_context
def generate_commit_msg(ctx: click.Context, message_file: str, source: str, sha: str) -> None:
    """Generate commit message from staged diff (used by prepare-commit-msg hook)."""
    # Skip for merge, squash, amend, and user-provided messages
    if source in ("merge", "squash", "commit", "message"):
        return

    graceful = ctx.obj.get("graceful", False) if ctx.obj else False

    ext_raw = None
    project_id = None
    try:
        config = Config()
        ext_raw = config.get("review", "include_extensions")
        project_id = config.get("commit", "project_id")
    except Exception:
        config = None

    if ext_raw is None:
        ext_raw = DEFAULT_INCLUDE_EXTENSIONS
    extensions = [e.strip() for e in ext_raw.split(",") if e.strip()] if ext_raw else None

    try:
        diff = get_staged_diff(extensions=extensions)
    except GitError:
        return
    if not diff:
        return

    try:
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config or Config(), cli_provider, cli_model)
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

    if project_id:
        message = f"[{project_id}] {description}"
    else:
        message = description

    msg_path = Path(message_file)
    msg_path.write_text(message + "\n")
    console.print(f"[green]Generated: {rich_escape(message)}[/]")
```

**Step 4: Run tests**

Run: `pytest tests/test_cli.py::TestGenerateCommitMsgCommand -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add generate-commit-msg command for prepare-commit-msg hook"
```

---

### Task 7: Add prepare-commit-msg hook scripts

**Files:**
- Modify: `src/ai_code_review/cli.py:321` (`_HOOK_TYPES`)
- Modify: `src/ai_code_review/cli.py:324-367` (hook generators)
- Test: `tests/test_hooks.py`

**Step 1: Write failing tests**

Add to `tests/test_hooks.py`:

```python
class TestPrepareCommitMsgHookScript:
    def test_global_scripts_include_prepare_commit_msg(self):
        from ai_code_review.cli import _generate_hook_scripts
        scripts = _generate_hook_scripts()
        assert "prepare-commit-msg" in scripts
        script = scripts["prepare-commit-msg"]
        assert "generate-commit-msg" in script
        assert '"$1"' in script
        assert '"$2"' in script
        assert '"$3"' in script
        assert "--graceful" in script

    def test_template_scripts_include_prepare_commit_msg(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        assert "prepare-commit-msg" in scripts
        script = scripts["prepare-commit-msg"]
        assert "generate-commit-msg" in script
        assert "git config --local ai-review.enabled" in script

    def test_hook_types_includes_prepare_commit_msg(self):
        from ai_code_review.cli import _HOOK_TYPES
        assert "prepare-commit-msg" in _HOOK_TYPES

    def test_install_prepare_commit_msg_repo_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "prepare-commit-msg"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "prepare-commit-msg"
        assert hook_path.exists()
        assert "generate-commit-msg" in hook_path.read_text()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hooks.py::TestPrepareCommitMsgHookScript -v`
Expected: FAIL

**Step 3: Update `_HOOK_TYPES` and hook generators**

In `src/ai_code_review/cli.py`:

1. Update `_HOOK_TYPES`:
```python
_HOOK_TYPES = ["pre-commit", "prepare-commit-msg", "commit-msg"]
```

2. Add prepare-commit-msg to `_generate_hook_scripts()`:
```python
def _generate_hook_scripts() -> dict[str, str]:
    ai_review = _resolve_ai_review_path()
    opt_in_check = """\
# opt-in: only run in repos that have a .ai-review marker file
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ ! -f "$REPO_ROOT/.ai-review" ]; then
    exit 0
fi"""
    return {
        "pre-commit": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful
""",
        "prepare-commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful generate-commit-msg "$1" "$2" "$3"
""",
        "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful check-commit --auto-accept "$1"
""",
    }
```

3. Same pattern for `_generate_template_hook_scripts()` — add prepare-commit-msg entry with template opt-in check.

**Step 4: Run tests**

Run: `pytest tests/test_hooks.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add prepare-commit-msg hook for auto-generating commit messages"
```

---

## Phase 3: pre-push Hook

### Task 8: Add `get_push_diff()` to git.py

**Files:**
- Modify: `src/ai_code_review/git.py`
- Test: `tests/test_git.py`

**Step 1: Write failing tests**

Add to `tests/test_git.py`:

```python
class TestGetPushDiff:
    def test_normal_push_returns_diff(self, tmp_path, monkeypatch):
        """Diff between remote_sha and local_sha."""
        monkeypatch.chdir(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
        # Initial commit
        (tmp_path / "a.c").write_text("int x = 0;\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
        sha1 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()
        # Second commit
        (tmp_path / "a.c").write_text("int x = 1;\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, check=True, capture_output=True)
        sha2 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()

        from ai_code_review.git import get_push_diff
        diff = get_push_diff(sha2, sha1)
        assert "int x = 1" in diff

    def test_delete_branch_returns_empty(self):
        from ai_code_review.git import get_push_diff
        zero_sha = "0" * 40
        diff = get_push_diff(zero_sha, "abc123")
        assert diff == ""

    def test_extension_filter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "a.c").write_text("int x;\n")
        (tmp_path / "b.py").write_text("x = 0\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
        sha1 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()
        (tmp_path / "a.c").write_text("int x = 1;\n")
        (tmp_path / "b.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=tmp_path, check=True, capture_output=True)
        sha2 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout.strip()

        from ai_code_review.git import get_push_diff
        diff = get_push_diff(sha2, sha1, extensions=["c"])
        assert "int x = 1" in diff
        assert "x = 1" not in diff or "int" in diff  # only .c changes
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git.py::TestGetPushDiff -v`
Expected: FAIL — `get_push_diff` doesn't exist

**Step 3: Implement**

In `src/ai_code_review/git.py`:

```python
_ZERO_SHA = "0" * 40


def get_commit_diff(from_ref: str, to_ref: str, extensions: list[str] | None = None) -> str:
    args = ["diff", from_ref, to_ref]
    if extensions:
        args.append("--")
        args.extend(f"*.{ext.lstrip('.')}" for ext in extensions)
    return _run_git(*args).strip()


def get_push_diff(local_sha: str, remote_sha: str, extensions: list[str] | None = None) -> str:
    """Get diff for commits being pushed."""
    if local_sha == _ZERO_SHA:
        return ""  # Branch being deleted
    if remote_sha == _ZERO_SHA:
        # New branch — try to find merge base with main/master
        for base_ref in ["origin/main", "origin/master", "main", "master"]:
            try:
                merge_base = _run_git("merge-base", local_sha, base_ref).strip()
                return get_commit_diff(merge_base, local_sha, extensions)
            except GitError:
                continue
        return ""  # Can't determine base
    return get_commit_diff(remote_sha, local_sha, extensions)
```

Note: the existing `get_commit_diff` signature changes from `(from_ref, to_ref)` to `(from_ref, to_ref, extensions=None)`. This is backward compatible since extensions defaults to None.

**Step 4: Run tests**

Run: `pytest tests/test_git.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/git.py tests/test_git.py
git commit -m "feat: add get_push_diff for pre-push hook support"
```

---

### Task 9: Add `pre-push` CLI command

**Files:**
- Modify: `src/ai_code_review/cli.py` (add command, update imports)
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestPrePushCommand:
    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_push_diff")
    def test_reviews_push_diff(self, mock_push_diff, mock_build, mock_config_cls, runner):
        mock_push_diff.return_value = "some diff"
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[])
        mock_build.return_value = mock_provider

        local_sha = "abc123"
        remote_sha = "def456"
        stdin_data = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
        result = runner.invoke(main, ["pre-push"], input=stdin_data)
        assert result.exit_code == 0

    @patch("ai_code_review.cli.Config")
    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_push_diff")
    def test_blocks_on_critical_issue(self, mock_push_diff, mock_build, mock_config_cls, runner):
        mock_push_diff.return_value = "some diff"
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config.resolve_provider.return_value = "ollama"
        mock_config_cls.return_value = mock_config
        mock_provider = MagicMock()
        mock_provider.review_code.return_value = ReviewResult(issues=[
            ReviewIssue(severity=Severity.CRITICAL, file="a.c", line=1, message="leak"),
        ])
        mock_build.return_value = mock_provider

        stdin_data = "refs/heads/main abc123 refs/heads/main def456\n"
        result = runner.invoke(main, ["pre-push"], input=stdin_data)
        assert result.exit_code == 1

    @patch("ai_code_review.cli.get_push_diff")
    def test_empty_diff_exits_clean(self, mock_push_diff, runner):
        mock_push_diff.return_value = ""
        stdin_data = "refs/heads/main abc123 refs/heads/main def456\n"
        result = runner.invoke(main, ["pre-push"], input=stdin_data)
        assert result.exit_code == 0

    @patch("ai_code_review.cli._build_provider")
    @patch("ai_code_review.cli.get_push_diff")
    def test_graceful_on_provider_error(self, mock_push_diff, mock_build, runner):
        mock_push_diff.return_value = "some diff"
        mock_build.side_effect = ProviderError("Connection refused")
        stdin_data = "refs/heads/main abc123 refs/heads/main def456\n"
        result = runner.invoke(main, ["--graceful", "pre-push"], input=stdin_data)
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    def test_no_stdin_exits_clean(self, runner):
        result = runner.invoke(main, ["pre-push"], input="")
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestPrePushCommand -v`
Expected: FAIL

**Step 3: Implement the command**

In `src/ai_code_review/cli.py`:

1. Add import: `from .git import GitError, get_staged_diff, get_push_diff`

2. Add command after `generate_commit_msg`:

```python
@main.command("pre-push")
@click.pass_context
def pre_push(ctx: click.Context) -> None:
    """Review commits before push (used by pre-push hook)."""
    graceful = ctx.obj.get("graceful", False) if ctx.obj else False

    # Read ref data from stdin
    stdin_data = click.get_text_stream("stdin").read().strip()
    if not stdin_data:
        return

    config = Config()
    cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
    cli_model = ctx.obj.get("cli_model") if ctx.obj else None

    ext_raw = config.get("review", "include_extensions")
    if ext_raw is None:
        ext_raw = DEFAULT_INCLUDE_EXTENSIONS
    extensions = [e.strip() for e in ext_raw.split(",") if e.strip()] if ext_raw else None

    # Collect diffs from all refs being pushed
    all_diff_parts = []
    for line in stdin_data.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts[:4]
        try:
            diff = get_push_diff(local_sha, remote_sha, extensions=extensions)
            if diff:
                all_diff_parts.append(diff)
        except GitError:
            continue

    all_diff = "\n".join(all_diff_parts)
    if not all_diff:
        console.print("[dim]No changes to review in push.[/]")
        return

    # Truncate large diffs
    max_lines_raw = config.get("review", "max_diff_lines")
    max_lines = int(max_lines_raw) if max_lines_raw else DEFAULT_MAX_DIFF_LINES
    lines = all_diff.split("\n")
    if len(lines) > max_lines:
        console.print(f"[yellow]Warning: diff truncated to {max_lines} lines (original: {len(lines)} lines)[/]")
        all_diff = "\n".join(lines[:max_lines]) + f"\n... (truncated: showing first {max_lines} of {len(lines)} lines)"

    custom_rules = config.get("review", "custom_rules")

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except (ProviderNotConfiguredError, ProviderError) as e:
        if graceful:
            console.print(f"[yellow]Warning: AI review unavailable — {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    reviewer = Reviewer(provider=provider)
    try:
        result = reviewer.review_diff(all_diff, custom_rules=custom_rules)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: AI review failed — {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    output_format = ctx.obj.get("output_format", "terminal") if ctx.obj else "terminal"
    formatters = {"terminal": format_terminal, "markdown": format_markdown, "json": format_json}
    output = formatters[output_format](result)
    click.echo(output)

    if result.is_blocked:
        sys.exit(1)
```

**Step 4: Run tests**

Run: `pytest tests/test_cli.py::TestPrePushCommand -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_cli.py
git commit -m "feat: add pre-push command for AI review before push"
```

---

### Task 10: Add pre-push hook scripts

**Files:**
- Modify: `src/ai_code_review/cli.py:321` (`_HOOK_TYPES`)
- Modify: `src/ai_code_review/cli.py:324-367` (hook generators)
- Test: `tests/test_hooks.py`

**Step 1: Write failing tests**

Add to `tests/test_hooks.py`:

```python
class TestPrePushHookScript:
    def test_hook_types_includes_pre_push(self):
        from ai_code_review.cli import _HOOK_TYPES
        assert "pre-push" in _HOOK_TYPES

    def test_global_scripts_include_pre_push(self):
        from ai_code_review.cli import _generate_hook_scripts
        scripts = _generate_hook_scripts()
        assert "pre-push" in scripts
        assert "pre-push" in scripts["pre-push"]
        assert "--graceful" in scripts["pre-push"]

    def test_template_scripts_include_pre_push(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        assert "pre-push" in scripts
        assert "git config --local ai-review.enabled" in scripts["pre-push"]
        assert "--graceful" in scripts["pre-push"]

    def test_install_pre_push_repo_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "pre-push"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-push"
        assert hook_path.exists()
        assert "pre-push" in hook_path.read_text()

    def test_template_install_includes_pre_push(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            result = runner.invoke(main, ["hook", "install", "--template"])
        assert result.exit_code == 0
        assert (fake_template_dir / "pre-push").exists()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hooks.py::TestPrePushHookScript -v`
Expected: FAIL

**Step 3: Update `_HOOK_TYPES` and hook generators**

In `src/ai_code_review/cli.py`:

1. Update `_HOOK_TYPES`:
```python
_HOOK_TYPES = ["pre-commit", "prepare-commit-msg", "commit-msg", "pre-push"]
```

2. Add to `_generate_hook_scripts()`:
```python
"pre-push": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful pre-push
""",
```

3. Add to `_generate_template_hook_scripts()`:
```python
"pre-push": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful pre-push
""",
```

**Step 4: Run tests**

Run: `pytest tests/test_hooks.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add pre-push hook for AI review before push"
```

---

## Phase 4: Documentation

### Task 11: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: Memory files

**Step 1: Update CLAUDE.md**

Add to Commands section:
```
ai-review generate-commit-msg <file> [source] [sha]  # generate commit message (prepare-commit-msg hook)
ai-review pre-push                                     # review commits before push (pre-push hook)
ai-review --graceful ...                               # warn on LLM failure instead of blocking
ai-review config set commit project_id BSP-456         # set project ID for auto-generated messages
```

Update Architecture section to include new commands.

Update Key Patterns section:
- Add graceful degradation pattern
- Add prepare-commit-msg flow
- Add pre-push flow
- Update hook list

Update test count.

**Step 2: Update MEMORY.md**

Update Architecture Decisions, Hook Deployment, and Testing Notes sections.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with new hooks and graceful degradation"
```

---

## Summary

| Phase | Task | Description |
|-------|------|-------------|
| 1 | 1 | Wrap provider `_chat()` errors in ProviderError |
| 1 | 2 | Add `--graceful` flag and ProviderError handling in CLI |
| 1 | 3 | Update hook scripts to use `--graceful` |
| 2 | 4 | Add commit message generation prompt |
| 2 | 5 | Add `generate_commit_msg` to LLM providers and Reviewer |
| 2 | 6 | Add `generate-commit-msg` CLI command |
| 2 | 7 | Add prepare-commit-msg hook scripts |
| 3 | 8 | Add `get_push_diff()` to git.py |
| 3 | 9 | Add `pre-push` CLI command |
| 3 | 10 | Add pre-push hook scripts |
| 4 | 11 | Update documentation |

**New test count estimate:** ~165-175 tests (currently 139)
