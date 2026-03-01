from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape as rich_escape

from .commit_check import check_commit_message
from .config import DEFAULT_INCLUDE_EXTENSIONS, DEFAULT_MAX_DIFF_LINES, Config
from .exceptions import ProviderError, ProviderNotConfiguredError
from .formatters import format_json, format_markdown, format_terminal
from .git import GitError, get_staged_diff
from .llm.base import LLMProvider
from .llm.enterprise import EnterpriseProvider
from .llm.ollama import OllamaProvider
from .llm.openai import OpenAIProvider
from .reviewer import Reviewer

console = Console()


def _build_provider(config: Config, cli_provider: str | None, cli_model: str | None) -> LLMProvider:
    provider_name = config.resolve_provider(cli_provider)
    if not provider_name:
        raise ProviderNotConfiguredError(
            "No provider configured. Available providers: ollama, openai, enterprise.\n"
            "Run: ai-review config set provider default <name>"
        )

    if provider_name == "ollama":
        base_url = config.get("ollama", "base_url") or "http://localhost:11434"
        model = cli_model or config.get("ollama", "model") or "codellama"
        timeout = float(config.get("ollama", "timeout") or 120)
        return OllamaProvider(base_url=base_url, model=model, timeout=timeout)

    elif provider_name == "openai":
        token = config.resolve_token("openai")
        if not token:
            env_var = config.get("openai", "api_key_env") or "OPENAI_API_KEY"
            raise ProviderNotConfiguredError(
                f"OpenAI API key not found. Set env var {env_var} "
                f"(or configure: ai-review config set openai api_key_env <VAR_NAME>)"
            )
        model = cli_model or config.get("openai", "model") or "gpt-4o"
        base_url = config.get("openai", "base_url")
        timeout = float(config.get("openai", "timeout") or 120)
        return OpenAIProvider(api_key=token, model=model, base_url=base_url, timeout=timeout)

    elif provider_name == "enterprise":
        token = config.resolve_token("enterprise") or ""
        base_url = config.get("enterprise", "base_url")
        if not base_url:
            raise ProviderNotConfiguredError(
                "Enterprise base_url not configured.\n"
                "Run: ai-review config set enterprise base_url <URL>"
            )
        api_path = config.get("enterprise", "api_path") or "/v1/chat/completions"
        model = cli_model or config.get("enterprise", "model") or "default"
        auth_type = config.get("enterprise", "auth_type") or "bearer"
        timeout = float(config.get("enterprise", "timeout") or 120)
        return EnterpriseProvider(
            base_url=base_url, api_path=api_path, model=model,
            auth_type=auth_type, auth_token=token, timeout=timeout,
        )

    raise ProviderNotConfiguredError(f"Unknown provider: {provider_name}")


@click.group(invoke_without_command=True)
@click.option("--provider", "cli_provider", default=None, help="LLM provider (ollama/openai/enterprise)")
@click.option("--model", "cli_model", default=None, help="Model name")
@click.option("--format", "output_format", default="terminal", type=click.Choice(["terminal", "markdown", "json"]))
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.option("--graceful", is_flag=True, help="Don't block on LLM failures (exit 0 instead of 1).")
@click.pass_context
def main(ctx: click.Context, cli_provider: str | None, cli_model: str | None, output_format: str, verbose: bool, graceful: bool) -> None:
    """AI-powered code review for Android BSP teams."""
    ctx.ensure_object(dict)
    ctx.obj["cli_provider"] = cli_provider
    ctx.obj["cli_model"] = cli_model
    ctx.obj["output_format"] = output_format
    ctx.obj["graceful"] = graceful

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="[DEBUG] %(message)s")
        logging.getLogger("ai_code_review").setLevel(logging.DEBUG)

    if ctx.invoked_subcommand is None:
        _review(ctx)


def _review(ctx: click.Context) -> None:
    config = Config()
    cli_provider = ctx.obj["cli_provider"]
    cli_model = ctx.obj["cli_model"]
    output_format = ctx.obj["output_format"]
    graceful = ctx.obj.get("graceful", False)

    ext_raw = config.get("review", "include_extensions")
    if ext_raw is None:
        ext_raw = DEFAULT_INCLUDE_EXTENSIONS
    extensions = [e.strip() for e in ext_raw.split(",") if e.strip()] if ext_raw else None

    try:
        diff = get_staged_diff(extensions=extensions)
    except GitError as e:
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    if not diff:
        if extensions:
            console.print(f"[dim]No staged changes matching {rich_escape(', '.join(f'.{e}' for e in extensions))}.[/]")
        else:
            console.print("[dim]No staged changes to review.[/]")
        return

    # Truncate large diffs
    max_lines_raw = config.get("review", "max_diff_lines")
    max_lines = int(max_lines_raw) if max_lines_raw else DEFAULT_MAX_DIFF_LINES
    lines = diff.split("\n")
    if len(lines) > max_lines:
        console.print(f"[yellow]Warning: diff truncated to {max_lines} lines (original: {len(lines)} lines)[/]")
        diff = "\n".join(lines[:max_lines]) + f"\n... (truncated: showing first {max_lines} of {len(lines)} lines)"

    custom_rules = config.get("review", "custom_rules")

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError as e:
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: LLM provider error: {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    reviewer = Reviewer(provider=provider)
    try:
        result = reviewer.review_diff(diff, custom_rules=custom_rules)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: LLM provider error: {rich_escape(str(e))}[/]")
            return
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    formatters = {"terminal": format_terminal, "markdown": format_markdown, "json": format_json}
    output = formatters[output_format](result)
    click.echo(output)

    if result.is_blocked:
        sys.exit(1)


@main.command("check-commit")
@click.argument("message_file", required=False)
@click.option("--auto-accept", is_flag=True, help="Auto-accept AI suggestion without prompt.")
@click.pass_context
def check_commit(ctx: click.Context, message_file: str | None, auto_accept: bool) -> None:
    """Check commit message format and optionally improve with AI."""
    if message_file:
        msg_path = Path(message_file)
        message = msg_path.read_text().strip()
    else:
        message = click.get_text_stream("stdin").readline().strip()
        msg_path = None

    # Step 1: Format check
    result = check_commit_message(message)
    if not result.valid:
        console.print(f"[bold red]{rich_escape(result.error)}[/]")
        sys.exit(1)
    console.print("[green]Commit message format OK.[/]")

    # Step 2: AI improvement (only when we have a file to update and a provider)
    if msg_path is None:
        return

    try:
        config = Config()
        cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
        cli_model = ctx.obj.get("cli_model") if ctx.obj else None
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError:
        # No provider configured — skip AI improvement silently
        return

    try:
        diff = get_staged_diff()
    except GitError:
        diff = ""

    if not diff:
        return

    graceful = ctx.obj.get("graceful", False) if ctx.obj else False

    reviewer = Reviewer(provider=provider)
    try:
        improved = reviewer.improve_commit_message(message, diff)
    except ProviderError as e:
        if graceful:
            console.print(f"[yellow]Warning: LLM provider error: {rich_escape(str(e))}[/]")
        else:
            console.print(f"[bold red]{rich_escape(str(e))}[/]")
        return

    if improved and improved.strip() != message:
        console.print(f"\n[dim]Original:[/]  {rich_escape(message)}")
        console.print(f"[bold]Suggested:[/] {rich_escape(improved)}")
        if auto_accept or os.environ.get("AI_REVIEW_AUTO_ACCEPT") == "1":
            choice = "a"
            console.print("[dim](non-interactive: auto-accept)[/]")
        else:
            choice = click.prompt(
                "[A]ccept / [E]dit / [S]kip",
                type=click.Choice(["a", "e", "s"], case_sensitive=False),
                default="a",
            )
        if choice == "a":
            msg_path.write_text(improved + "\n")
            console.print("[green]Commit message updated.[/]")
        elif choice == "e":
            edited = click.edit(improved)
            if edited:
                msg_path.write_text(edited)
                console.print("[green]Commit message updated.[/]")
        # "s" → do nothing, keep original


@main.command("health-check")
@click.pass_context
def health_check_cmd(ctx: click.Context) -> None:
    """Check LLM provider connectivity."""
    config = Config()
    cli_provider = ctx.obj.get("cli_provider") if ctx.obj else None
    cli_model = ctx.obj.get("cli_model") if ctx.obj else None

    try:
        provider = _build_provider(config, cli_provider, cli_model)
    except ProviderNotConfiguredError as e:
        console.print(f"[bold red]{rich_escape(str(e))}[/]")
        sys.exit(1)

    provider_name = config.resolve_provider(cli_provider)
    model = cli_model or config.get(provider_name, "model") or "default"
    console.print(f"Provider: {rich_escape(provider_name)} ({rich_escape(model)})")

    ok, msg = provider.health_check()
    if ok:
        console.print(f"[green]Status: OK ({rich_escape(msg)})[/]")
    else:
        console.print(f"[bold red]Status: FAILED — {rich_escape(msg)}[/]")
        sys.exit(1)


@main.group("config")
def config_group() -> None:
    """Manage configuration."""
    pass


@config_group.command("set")
@click.argument("section")
@click.argument("key")
@click.argument("value")
def config_set(section: str, key: str, value: str) -> None:
    """Set a config value: ai-review config set <section> <key> <value>"""
    config = Config()
    config.set(section, key, value)
    console.print(f"[green]Set {rich_escape(section)}.{rich_escape(key)} = {rich_escape(value)}[/]")


@config_group.command("get")
@click.argument("section")
@click.argument("key")
def config_get(section: str, key: str) -> None:
    """Get a config value: ai-review config get <section> <key>"""
    config = Config()
    value = config.get(section, key)
    if value is None:
        console.print(f"[dim]{section}.{key} is not set[/]")
    else:
        console.print(value)


@config_group.command("show")
@click.argument("section", required=False)
def config_show(section: str | None) -> None:
    """Show current configuration."""
    config = Config()
    data = config._data

    if not data:
        console.print("[dim]No configuration set.[/]")
        return

    if section:
        if section not in data:
            console.print(f"[dim]Section '{rich_escape(section)}' not found.[/]")
            return
        _print_config_section(section, data[section])
    else:
        for sect_name, sect_data in data.items():
            _print_config_section(sect_name, sect_data)
            console.print()


def _print_config_section(name: str, data: dict) -> None:
    console.print(f"[bold]{rich_escape('[' + name + ']')}[/]")
    for key, value in data.items():
        console.print(f"  {rich_escape(key)} = {rich_escape(str(value))}")


# --- Hook management ---

_GLOBAL_HOOKS_DIR = Path.home() / ".config" / "ai-code-review" / "hooks"
_TEMPLATE_HOOKS_DIR = Path.home() / ".config" / "ai-code-review" / "template" / "hooks"


def _resolve_ai_review_path() -> str:
    """Find the absolute path to the ai-review executable."""
    import shutil

    # 1. Check if ai-review is in PATH
    found = shutil.which("ai-review")
    if found:
        return found

    # 2. Check relative to this Python interpreter (venv/bin/)
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "ai-review"
    if candidate.exists():
        return str(candidate)

    return "ai-review"


_HOOK_TYPES = ["pre-commit", "commit-msg"]


def _generate_hook_scripts() -> dict[str, str]:
    """Generate hook scripts with the resolved ai-review path."""
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
        "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful check-commit --auto-accept "$1"
""",
    }


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
{ai_review} --graceful
""",
        "commit-msg": f"""#!/usr/bin/env bash
# Installed by ai-code-review
{opt_in_check}
{ai_review} --graceful check-commit --auto-accept "$1"
""",
    }


@main.group("hook")
def hook_group() -> None:
    """Manage git hooks (global or per-repo)."""
    pass


@hook_group.command("install")
@click.option("--global", "global_install", is_flag=True, help="Install globally via core.hooksPath (all repos).")
@click.option("--template", "template_install", is_flag=True, help="Install via init.templateDir (recommended for Android).")
@click.argument("hook_type", required=False, type=click.Choice(_HOOK_TYPES))
def hook_install(global_install: bool, template_install: bool, hook_type: str | None) -> None:
    """Install git hooks. Use --template for Android multi-repo teams."""
    if global_install and template_install:
        console.print("[bold red]Cannot use --global and --template together.[/]")
        sys.exit(1)
    if template_install:
        _install_template_hooks()
    elif global_install:
        _install_global_hooks()
    elif hook_type:
        _install_repo_hook(hook_type)
    else:
        console.print("[bold red]Specify a hook type, --global, or --template.[/]")
        sys.exit(1)


@hook_group.command("uninstall")
@click.option("--global", "global_uninstall", is_flag=True, help="Remove global hooks and core.hooksPath.")
@click.option("--template", "template_uninstall", is_flag=True, help="Remove template hooks and init.templateDir.")
@click.argument("hook_type", required=False, type=click.Choice(_HOOK_TYPES))
def hook_uninstall(global_uninstall: bool, template_uninstall: bool, hook_type: str | None) -> None:
    """Uninstall git hooks."""
    if global_uninstall and template_uninstall:
        console.print("[bold red]Cannot use --global and --template together.[/]")
        sys.exit(1)
    if template_uninstall:
        _uninstall_template_hooks()
    elif global_uninstall:
        _uninstall_global_hooks()
    elif hook_type:
        _uninstall_repo_hook(hook_type)
    else:
        console.print("[bold red]Specify a hook type, --global, or --template.[/]")
        sys.exit(1)


@hook_group.command("status")
def hook_status() -> None:
    """Show installed hooks (template, global, and current repo)."""
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
    except (subprocess.CalledProcessError, OSError):
        console.print("  [dim]not configured[/]")

    # Global hooks status
    console.print("\n[bold]Global hooks:[/]")
    try:
        result = subprocess.run(
            ["git", "config", "--global", "core.hooksPath"],
            capture_output=True, text=True,
        )
        hooks_path = result.stdout.strip()
        if hooks_path:
            console.print(f"  core.hooksPath = {hooks_path}")
            hooks_dir = Path(hooks_path)
            for hook_type in _HOOK_TYPES:
                hook_path = hooks_dir / hook_type
                if hook_path.exists() and "ai-review" in hook_path.read_text():
                    console.print(f"  [green]{hook_type}: installed[/]")
                else:
                    console.print(f"  [dim]{hook_type}: not installed[/]")
        else:
            console.print("  [dim]not configured[/]")
    except (subprocess.CalledProcessError, OSError):
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


@hook_group.command("enable")
def hook_enable() -> None:
    """Enable AI review for current repo (sets git config --local)."""
    import subprocess

    try:
        from .git import _run_git
        _run_git("rev-parse", "--git-dir")
    except (subprocess.CalledProcessError, OSError, GitError):
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
    except (subprocess.CalledProcessError, OSError, GitError):
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


def _install_global_hooks() -> None:
    import subprocess

    hook_scripts = _generate_hook_scripts()
    _GLOBAL_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for hook_type, script in hook_scripts.items():
        hook_path = _GLOBAL_HOOKS_DIR / hook_type
        hook_path.write_text(script)
        hook_path.chmod(0o755)
        console.print(f"  [green]Created {hook_path}[/]")

    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(_GLOBAL_HOOKS_DIR)],
        check=True,
    )
    console.print(f"\n[green]Global hooks installed.[/]")
    console.print(f"[dim]core.hooksPath → {_GLOBAL_HOOKS_DIR}[/]")
    console.print("[dim]Hooks only activate in repos with a .ai-review marker file.[/]")
    console.print("[dim]Enable a repo: touch /path/to/repo/.ai-review[/]")


def _uninstall_global_hooks() -> None:
    import subprocess

    for hook_type in _HOOK_TYPES:
        hook_path = _GLOBAL_HOOKS_DIR / hook_type
        if hook_path.exists():
            hook_path.unlink()
            console.print(f"  [green]Removed {hook_path}[/]")

    try:
        subprocess.run(
            ["git", "config", "--global", "--unset", "core.hooksPath"],
            check=True, capture_output=True,
        )
        console.print("[green]Global hooks uninstalled (core.hooksPath cleared).[/]")
    except subprocess.CalledProcessError:
        console.print("[dim]core.hooksPath was not set.[/]")


def _install_template_hooks() -> None:
    import subprocess

    # Check for conflicting core.hooksPath
    check = subprocess.run(
        ["git", "config", "--global", "core.hooksPath"],
        capture_output=True, text=True,
    )
    if check.stdout.strip():
        console.print(f"[bold yellow]Warning: core.hooksPath is set to {check.stdout.strip()}[/]")
        console.print("[yellow]core.hooksPath overrides .git/hooks/ — template hooks won't run.[/]")
        console.print("[yellow]Run 'ai-review hook uninstall --global' first.[/]")

    hook_scripts = _generate_template_hook_scripts()
    _TEMPLATE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for hook_type, script in hook_scripts.items():
        hook_path = _TEMPLATE_HOOKS_DIR / hook_type
        hook_path.write_text(script)
        hook_path.chmod(0o755)
        console.print(f"  [green]Created {hook_path}[/]")

    template_dir = _TEMPLATE_HOOKS_DIR.parent
    subprocess.run(
        ["git", "config", "--global", "init.templateDir", str(template_dir)],
        check=True,
    )
    console.print(f"\n[green]Template hooks installed.[/]")
    console.print(f"[dim]init.templateDir → {template_dir}[/]")
    console.print("[dim]New clones will auto-copy hooks to .git/hooks/[/]")
    console.print("[dim]Existing repos: run 'git init' to copy hooks[/]")
    console.print("[dim]Enable a repo: git config --local ai-review.enabled true[/]")


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


def _install_repo_hook(hook_type: str) -> None:
    hooks_dir = _get_repo_hooks_dir()
    hook_path = hooks_dir / hook_type
    hook_scripts = _generate_hook_scripts()
    hook_path.write_text(hook_scripts[hook_type])
    hook_path.chmod(0o755)
    console.print(f"[green]Installed {hook_type} hook in current repo.[/]")


def _uninstall_repo_hook(hook_type: str) -> None:
    hooks_dir = _get_repo_hooks_dir()
    hook_path = hooks_dir / hook_type
    if hook_path.exists():
        hook_path.unlink()
        console.print(f"[green]Removed {hook_type} hook.[/]")
    else:
        console.print(f"[dim]{hook_type} hook is not installed.[/]")


def _get_repo_hooks_dir() -> Path:
    try:
        from .git import _run_git
        git_dir = _run_git("rev-parse", "--git-dir").strip()
        hooks_dir = Path(git_dir) / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        return hooks_dir
    except (subprocess.CalledProcessError, OSError, GitError):
        console.print("[bold red]Not in a git repository.[/]")
        sys.exit(1)
