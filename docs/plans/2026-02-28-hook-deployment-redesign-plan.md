# Hook 部署機制重構 — 實作計畫

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 將 hook 部署從 `.ai-review` 標記檔 + `core.hooksPath` 改為 `init.templateDir` + `git config --local` opt-in，實現零 repo 檔案污染。

**Architecture:** 新增 `--template` 安裝模式，hook 腳本寫入 `~/.config/ai-code-review/template/hooks/`，透過 `init.templateDir` 自動複製到 `.git/hooks/`。Opt-in 使用 `git config --local ai-review.enabled true` 取代 `.ai-review` 標記檔。

**Tech Stack:** Python 3.10+, click CLI, subprocess (git config), pytest + CliRunner + monkeypatch

**Design doc:** `docs/plans/2026-02-28-hook-deployment-redesign.md`

---

### Task 1: Template hook 腳本生成

**Files:**
- Modify: `src/ai_code_review/cli.py:236-256` (`_generate_hook_scripts`)
- Modify: `src/ai_code_review/cli.py:212` (`_GLOBAL_HOOKS_DIR` 旁新增 `_TEMPLATE_HOOKS_DIR`)
- Test: `tests/test_hooks.py`

**Step 1: 寫測試 — 驗證 template hook 腳本使用 `git config --local` opt-in**

在 `tests/test_hooks.py` 新增：

```python
class TestTemplateHookScripts:
    def test_template_scripts_use_git_config_opt_in(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        for hook_type in ["pre-commit", "commit-msg"]:
            script = scripts[hook_type]
            assert "git config --local ai-review.enabled" in script
            assert ".ai-review" not in script
            assert "ai-review" in script

    def test_template_scripts_contain_required_commands(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        assert "ai-review" in scripts["pre-commit"]
        assert "check-commit" in scripts["commit-msg"]
```

**Step 2: 跑測試確認失敗**

Run: `pytest tests/test_hooks.py::TestTemplateHookScripts -v`
Expected: FAIL — `ImportError: cannot import name '_generate_template_hook_scripts'`

**Step 3: 實作 `_generate_template_hook_scripts()` 和 `_TEMPLATE_HOOKS_DIR`**

在 `cli.py` 的 `_GLOBAL_HOOKS_DIR` 下方新增：

```python
_TEMPLATE_HOOKS_DIR = Path.home() / ".config" / "ai-code-review" / "template" / "hooks"
```

在 `_generate_hook_scripts()` 下方新增：

```python
def _generate_template_hook_scripts() -> dict[str, str]:
    """Generate hook scripts that use git config --local for opt-in."""
    ai_review = _resolve_ai_review_path()
    opt_in_check = """\
# opt-in: check git local config
enabled=$(git config --local ai-review.enabled 2>/dev/null)
if [ "$enabled" != "true" ]; then
    exit 0
fi"""
    return {
        "pre-commit": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review}
""",
        "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} check-commit --auto-accept "$1"
""",
    }
```

**Step 4: 跑測試確認通過**

Run: `pytest tests/test_hooks.py::TestTemplateHookScripts -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add template hook script generation with git config opt-in"
```

---

### Task 2: `hook install --template` 指令

**Files:**
- Modify: `src/ai_code_review/cli.py:265-276` (`hook_install` command)
- Test: `tests/test_hooks.py`

**Step 1: 寫測試 — 驗證 `--template` 建立檔案並設定 `init.templateDir`**

```python
class TestTemplateHookInstall:
    def test_installs_template_hooks(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "install", "--template"])

        assert result.exit_code == 0
        assert (fake_template_dir / "pre-commit").exists()
        assert (fake_template_dir / "commit-msg").exists()
        assert "git config --local ai-review.enabled" in (fake_template_dir / "pre-commit").read_text()
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "init.templateDir",
             str(fake_template_dir.parent)],
            check=True,
        )

    def test_template_hook_scripts_are_executable(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run"):
            runner.invoke(main, ["hook", "install", "--template"])

        for hook_type in ["pre-commit", "commit-msg"]:
            hook_path = fake_template_dir / hook_type
            assert hook_path.stat().st_mode & 0o755
```

**Step 2: 跑測試確認失敗**

Run: `pytest tests/test_hooks.py::TestTemplateHookInstall -v`
Expected: FAIL — no such option `--template`

**Step 3: 實作 `--template` 選項和 `_install_template_hooks()`**

修改 `hook_install` command 加入 `--template` 選項：

```python
@hook_group.command("install")
@click.option("--template", "template_install", is_flag=True, help="Install via init.templateDir (recommended for Android).")
@click.argument("hook_type", required=False, type=click.Choice(_HOOK_TYPES))
def hook_install(template_install: bool, hook_type: str | None) -> None:
    """Install git hooks. Use --template for Android multi-repo teams."""
    if template_install:
        _install_template_hooks()
    elif hook_type:
        _install_repo_hook(hook_type)
    else:
        console.print("[bold red]Specify a hook type or --template.[/]")
        sys.exit(1)
```

新增 `_install_template_hooks()`：

```python
def _install_template_hooks() -> None:
    import subprocess

    hook_scripts = _generate_template_hook_scripts()
    _TEMPLATE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for hook_type, script in hook_scripts.items():
        hook_path = _TEMPLATE_HOOKS_DIR / hook_type
        hook_path.write_text(script)
        hook_path.chmod(0o755)
        console.print(f"  [green]Created {hook_path}[/]")

    template_dir = _TEMPLATE_HOOKS_DIR.parent  # ~/.config/ai-code-review/template
    subprocess.run(
        ["git", "config", "--global", "init.templateDir", str(template_dir)],
        check=True,
    )
    console.print(f"\n[green]Template hooks installed.[/]")
    console.print(f"[dim]init.templateDir → {template_dir}[/]")
    console.print("[dim]New clones will auto-copy hooks to .git/hooks/[/]")
    console.print("[dim]Existing repos: run 'git init' to copy hooks[/]")
    console.print("[dim]Enable a repo: git config --local ai-review.enabled true[/]")
```

**Step 4: 跑測試確認通過**

Run: `pytest tests/test_hooks.py::TestTemplateHookInstall -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add hook install --template command"
```

---

### Task 3: `hook uninstall --template` 指令

**Files:**
- Modify: `src/ai_code_review/cli.py:279-290` (`hook_uninstall` command)
- Test: `tests/test_hooks.py`

**Step 1: 寫測試**

```python
class TestTemplateHookUninstall:
    def test_uninstalls_template_hooks(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        fake_template_dir.mkdir(parents=True)
        (fake_template_dir / "pre-commit").write_text("#!/bin/sh\nai-review")
        (fake_template_dir / "commit-msg").write_text("#!/bin/sh\nai-review check-commit")

        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "uninstall", "--template"])

        assert result.exit_code == 0
        assert not (fake_template_dir / "pre-commit").exists()
        assert not (fake_template_dir / "commit-msg").exists()
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "--unset", "init.templateDir"],
            check=True, capture_output=True,
        )
```

**Step 2: 跑測試確認失敗**

Run: `pytest tests/test_hooks.py::TestTemplateHookUninstall -v`
Expected: FAIL — no such option `--template`

**Step 3: 實作**

修改 `hook_uninstall` command 加入 `--template` 選項：

```python
@hook_group.command("uninstall")
@click.option("--template", "template_uninstall", is_flag=True, help="Remove template hooks and init.templateDir.")
@click.argument("hook_type", required=False, type=click.Choice(_HOOK_TYPES))
def hook_uninstall(template_uninstall: bool, hook_type: str | None) -> None:
    """Uninstall git hooks."""
    if template_uninstall:
        _uninstall_template_hooks()
    elif hook_type:
        _uninstall_repo_hook(hook_type)
    else:
        console.print("[bold red]Specify a hook type or --template.[/]")
        sys.exit(1)
```

新增 `_uninstall_template_hooks()`：

```python
def _uninstall_template_hooks() -> None:
    import subprocess

    for hook_type in _HOOK_TYPES:
        hook_path = _TEMPLATE_HOOKS_DIR / hook_type
        if hook_path.exists():
            hook_path.unlink()
            console.print(f"  [green]Removed {hook_path}[/]")

    try:
        subprocess.run(
            ["git", "config", "--global", "--unset", "init.templateDir"],
            check=True, capture_output=True,
        )
        console.print("[green]Template hooks uninstalled (init.templateDir cleared).[/]")
    except subprocess.CalledProcessError:
        console.print("[dim]init.templateDir was not set.[/]")
```

**Step 4: 跑測試確認通過**

Run: `pytest tests/test_hooks.py::TestTemplateHookUninstall -v`
Expected: 1 passed

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add hook uninstall --template command"
```

---

### Task 4: `hook enable` / `hook disable` 指令

**Files:**
- Modify: `src/ai_code_review/cli.py` (hook_group 下新增 enable/disable commands)
- Test: `tests/test_hooks.py`

**Step 1: 寫測試**

```python
class TestHookEnableDisable:
    def test_enable_sets_git_config(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "enable"])
        assert result.exit_code == 0
        # Verify git config was set
        config_result = subprocess.run(
            ["git", "config", "--local", "ai-review.enabled"],
            capture_output=True, text=True, cwd=git_repo,
        )
        assert config_result.stdout.strip() == "true"

    def test_disable_unsets_git_config(self, runner, git_repo):
        # First enable
        subprocess.run(
            ["git", "config", "--local", "ai-review.enabled", "true"],
            cwd=git_repo, check=True,
        )
        result = runner.invoke(main, ["hook", "disable"])
        assert result.exit_code == 0
        config_result = subprocess.run(
            ["git", "config", "--local", "ai-review.enabled"],
            capture_output=True, text=True, cwd=git_repo,
        )
        assert config_result.returncode != 0  # key not found

    def test_enable_not_in_git_repo(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["hook", "enable"])
        assert result.exit_code != 0
```

**Step 2: 跑測試確認失敗**

Run: `pytest tests/test_hooks.py::TestHookEnableDisable -v`
Expected: FAIL — `Usage: main hook [OPTIONS] COMMAND` / no such command 'enable'

**Step 3: 實作 `enable` / `disable` commands**

在 `hook_group` 下新增：

```python
@hook_group.command("enable")
def hook_enable() -> None:
    """Enable AI review for current repo (sets git config --local)."""
    import subprocess

    try:
        from .git import _run_git
        _run_git("rev-parse", "--git-dir")
    except Exception:
        console.print("[bold red]Not in a git repository.[/]")
        sys.exit(1)

    subprocess.run(
        ["git", "config", "--local", "ai-review.enabled", "true"],
        check=True,
    )
    console.print("[green]AI review enabled for this repo.[/]")


@hook_group.command("disable")
def hook_disable() -> None:
    """Disable AI review for current repo (unsets git config --local)."""
    import subprocess

    try:
        from .git import _run_git
        _run_git("rev-parse", "--git-dir")
    except Exception:
        console.print("[bold red]Not in a git repository.[/]")
        sys.exit(1)

    try:
        subprocess.run(
            ["git", "config", "--local", "--unset", "ai-review.enabled"],
            check=True, capture_output=True,
        )
        console.print("[green]AI review disabled for this repo.[/]")
    except subprocess.CalledProcessError:
        console.print("[dim]AI review was not enabled for this repo.[/]")
```

**Step 4: 跑測試確認通過**

Run: `pytest tests/test_hooks.py::TestHookEnableDisable -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: add hook enable/disable commands for per-repo opt-in"
```

---

### Task 5: 更新 `hook status` 顯示 template 和 enabled 狀態

**Files:**
- Modify: `src/ai_code_review/cli.py:293-331` (`hook_status`)
- Test: `tests/test_hooks.py`

**Step 1: 寫測試**

```python
class TestHookStatusTemplate:
    def test_shows_template_status(self, runner, git_repo, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        fake_template_dir.mkdir(parents=True)
        (fake_template_dir / "pre-commit").write_text("#!/bin/sh\nai-review")
        (fake_template_dir / "commit-msg").write_text("#!/bin/sh\nai-review check-commit")

        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if "init.templateDir" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=str(fake_template_dir.parent))
                return subprocess.CompletedProcess(cmd, 0, stdout="")
            mock_run.side_effect = side_effect
            result = runner.invoke(main, ["hook", "status"])

        assert result.exit_code == 0
        assert "Template hooks" in result.output
        assert "init.templateDir" in result.output

    def test_shows_enabled_status(self, runner, git_repo):
        subprocess.run(
            ["git", "config", "--local", "ai-review.enabled", "true"],
            cwd=git_repo, check=True,
        )
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "ai-review.enabled = true" in result.output
```

**Step 2: 跑測試確認失敗**

Run: `pytest tests/test_hooks.py::TestHookStatusTemplate -v`
Expected: FAIL — "Template hooks" not in output

**Step 3: 重寫 `hook_status`**

```python
@hook_group.command("status")
def hook_status() -> None:
    """Show installed hooks (template and current repo)."""
    import subprocess

    # Template hooks status
    console.print("[bold]Template hooks:[/]")
    try:
        result = subprocess.run(
            ["git", "config", "--global", "init.templateDir"],
            capture_output=True, text=True,
        )
        template_path = result.stdout.strip()
        if template_path:
            console.print(f"  init.templateDir = {template_path}")
            hooks_dir = Path(template_path) / "hooks"
            for hook_type in _HOOK_TYPES:
                hook_path = hooks_dir / hook_type
                if hook_path.exists() and "ai-review" in hook_path.read_text():
                    console.print(f"  [green]{hook_type}: installed[/]")
                else:
                    console.print(f"  [dim]{hook_type}: not installed[/]")
        else:
            console.print("  [dim]not configured[/]")
    except Exception:
        console.print("  [dim]not configured[/]")

    # Current repo status
    console.print("\n[bold]Current repo:[/]")
    try:
        # Check ai-review.enabled
        result = subprocess.run(
            ["git", "config", "--local", "ai-review.enabled"],
            capture_output=True, text=True,
        )
        enabled = result.stdout.strip()
        if enabled:
            console.print(f"  ai-review.enabled = {enabled}")
        else:
            console.print("  [dim]ai-review.enabled: not set[/]")

        # Check repo hooks
        hooks_dir = _get_repo_hooks_dir()
        for hook_type in _HOOK_TYPES:
            hook_path = hooks_dir / hook_type
            if hook_path.exists() and "ai-review" in hook_path.read_text():
                console.print(f"  [green]{hook_type}: installed[/]")
            else:
                console.print(f"  [dim]{hook_type}: not installed[/]")
    except SystemExit:
        console.print("  [dim]not in a git repository[/]")
```

**Step 4: 跑測試確認通過**

Run: `pytest tests/test_hooks.py -v`
Expected: 全部通過（含既有測試 + 新增測試）

**Step 5: Commit**

```bash
git add src/ai_code_review/cli.py tests/test_hooks.py
git commit -m "feat: update hook status to show template and enabled state"
```

---

### Task 6: 跑全部測試確認無 regression

**Files:** 無修改

**Step 1: 跑全部測試**

Run: `pytest -v`
Expected: 全部通過

**Step 2: 修復任何失敗的既有測試**

如有失敗，分析原因並修正。特別注意：
- `TestHookStatus` 的既有測試可能因 output format 變更而失敗
- `hook_install` / `hook_uninstall` 的錯誤訊息可能已變更

**Step 3: Commit（如有修正）**

```bash
git add -u
git commit -m "fix: resolve test regressions from hook redesign"
```

---

### Task 7: 更新文件 — SOP

**Files:**
- Modify: `docs/SOP.md`

**Step 1: 更新 SOP Step 3 和 Step 4**

更新安裝流程，使用 `--template` 作為唯一推薦方案。

使用 `git config --local` 和 `hook enable/disable` 作為 opt-in 機制。

更新 hook 執行流程圖，使用 `git config --local ai-review.enabled` 檢查。

更新啟用/停用範例，使用 `ai-review hook enable` / `disable`。

更新快速安裝腳本。

**Step 2: Commit**

```bash
git add docs/SOP.md
git commit -m "docs: update SOP with template hooks and git config opt-in"
```

---

### Task 8: 更新文件 — README.md 和 CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Step 1: 更新 README.md**

更新 Hook Setup 段落，以 Template hooks 為唯一推薦方案。

新增 `hook enable` / `hook disable` 說明。

**Step 2: 更新 CLAUDE.md**

更新 Commands 段落，移除 `--global` 指令。

更新 Hook Deployment 段落，移除 global hooks 說明。

更新 Key Patterns 段落的 opt-in 機制說明。

**Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: update README and CLAUDE.md with template hook deployment"
```

---

### Task 9: 最終驗證

**Step 1: 跑全部測試**

Run: `pytest -v`
Expected: 全部通過

**Step 2: 驗證 CLI help 輸出**

Run: `ai-review hook install --help`
Expected: 顯示 `--template` 選項

Run: `ai-review hook --help`
Expected: 顯示 `enable`、`disable`、`install`、`uninstall`、`status` commands

**Step 3: Push**

```bash
git push
```
