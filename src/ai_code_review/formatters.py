from __future__ import annotations

import json

from rich.console import Console

from .llm.base import ReviewResult, Severity

_SEVERITY_ICONS = {
    Severity.CRITICAL: "\u274c",
    Severity.ERROR: "\u274c",
    Severity.WARNING: "\u26a0\ufe0f",
    Severity.INFO: "\u2139\ufe0f",
}

_SEVERITY_STYLES = {
    Severity.CRITICAL: "bold red",
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.INFO: "dim",
}


def format_terminal(result: ReviewResult) -> str:
    console = Console(record=True, force_terminal=True)

    if not result.issues:
        console.print("\n[bold green]\u2705 No issues found — code looks clean![/]")
        return console.export_text()

    console.print(f"\n[bold]\U0001f50d AI Code Review — {len(result.issues)} issue(s) found[/]\n")
    for issue in result.issues:
        icon = _SEVERITY_ICONS[issue.severity]
        style = _SEVERITY_STYLES[issue.severity]
        console.print(
            f"  {icon} [{style}][{issue.severity.value}][/] "
            f"[bold]{issue.file}:{issue.line}[/]"
        )
        console.print(f"     {issue.message}\n")

    summary = result.summary
    parts = [f"{count} {name}" for name, count in summary.items() if count > 0]
    console.print(f"[dim]{'─' * 50}[/]")
    console.print(f"Summary: {', '.join(parts)}")

    if result.is_blocked:
        console.print("[bold red]\u274c Commit blocked (critical/error found)[/]")
    else:
        console.print("[bold green]\u2705 Commit allowed (warnings only)[/]")

    return console.export_text()


def format_markdown(result: ReviewResult) -> str:
    lines = ["# AI Code Review Report\n"]
    if not result.issues:
        lines.append("No issues found.\n")
        return "\n".join(lines)

    lines.append("| Severity | File | Line | Issue |")
    lines.append("|----------|------|------|-------|")
    for issue in result.issues:
        lines.append(f"| {issue.severity.value} | {issue.file} | {issue.line} | {issue.message} |")

    summary = result.summary
    parts = [f"{count} {name}" for name, count in summary.items() if count > 0]
    lines.append(f"\n**Summary:** {', '.join(parts)}")
    lines.append(f"**Blocked:** {'Yes' if result.is_blocked else 'No'}")
    return "\n".join(lines)


def format_json(result: ReviewResult) -> str:
    data = {
        "summary": result.summary,
        "blocked": result.is_blocked,
        "issues": [
            {
                "severity": issue.severity.value,
                "file": issue.file,
                "line": issue.line,
                "message": issue.message,
            }
            for issue in result.issues
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
