from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from .commit_check import check_commit_message
from .config import Config
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
        console.print("[bold red]No provider configured. Run: ai-review config set provider default <name>[/]")
        sys.exit(1)

    if provider_name == "ollama":
        base_url = config.get("ollama", "base_url") or "http://localhost:11434"
        model = cli_model or config.get("ollama", "model") or "codellama"
        return OllamaProvider(base_url=base_url, model=model)

    elif provider_name == "openai":
        token = config.resolve_token("openai")
        if not token:
            console.print("[bold red]OpenAI API key not found. Set the env var specified in config.[/]")
            sys.exit(1)
        model = cli_model or config.get("openai", "model") or "gpt-4o"
        base_url = config.get("openai", "base_url")
        return OpenAIProvider(api_key=token, model=model, base_url=base_url)

    elif provider_name == "enterprise":
        token = config.resolve_token("enterprise") or ""
        base_url = config.get("enterprise", "base_url")
        if not base_url:
            console.print("[bold red]Enterprise base_url not configured.[/]")
            sys.exit(1)
        api_path = config.get("enterprise", "api_path") or "/v1/chat/completions"
        model = cli_model or config.get("enterprise", "model") or "default"
        auth_type = config.get("enterprise", "auth_type") or "bearer"
        return EnterpriseProvider(
            base_url=base_url, api_path=api_path, model=model,
            auth_type=auth_type, auth_token=token,
        )

    console.print(f"[bold red]Unknown provider: {provider_name}[/]")
    sys.exit(1)


@click.group(invoke_without_command=True)
@click.option("--provider", "cli_provider", default=None, help="LLM provider (ollama/openai/enterprise)")
@click.option("--model", "cli_model", default=None, help="Model name")
@click.option("--format", "output_format", default="terminal", type=click.Choice(["terminal", "markdown", "json"]))
@click.pass_context
def main(ctx: click.Context, cli_provider: str | None, cli_model: str | None, output_format: str) -> None:
    """AI-powered code review for Android BSP teams."""
    ctx.ensure_object(dict)
    ctx.obj["cli_provider"] = cli_provider
    ctx.obj["cli_model"] = cli_model
    ctx.obj["output_format"] = output_format

    if ctx.invoked_subcommand is None:
        _review(ctx)


def _review(ctx: click.Context) -> None:
    config = Config()
    cli_provider = ctx.obj["cli_provider"]
    cli_model = ctx.obj["cli_model"]
    output_format = ctx.obj["output_format"]

    try:
        diff = get_staged_diff()
    except GitError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)

    if not diff:
        console.print("[dim]No staged changes to review.[/]")
        return

    provider = _build_provider(config, cli_provider, cli_model)
    reviewer = Reviewer(provider=provider)
    result = reviewer.review_diff(diff)

    formatters = {"terminal": format_terminal, "markdown": format_markdown, "json": format_json}
    output = formatters[output_format](result)
    click.echo(output)

    if result.is_blocked:
        sys.exit(1)


@main.command("check-commit")
@click.argument("message_file", required=False)
def check_commit(message_file: str | None) -> None:
    """Check commit message format. Reads from file path (for git hook) or stdin."""
    if message_file:
        with open(message_file) as f:
            message = f.read().strip()
    else:
        message = click.get_text_stream("stdin").readline().strip()

    result = check_commit_message(message)
    if not result.valid:
        console.print(f"[bold red]{result.error}[/]")
        sys.exit(1)
    console.print("[green]Commit message format OK.[/]")


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
    console.print(f"[green]Set {section}.{key} = {value}[/]")


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
