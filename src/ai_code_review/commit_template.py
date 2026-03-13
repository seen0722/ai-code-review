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
    description: str | None = None,
    test: str,
    modified_files: list[str],
    bug_id: str | None = None,
    symptom: str | None = None,
    root_cause: str | None = None,
    solution: str | None = None,
) -> str:
    """Assemble a structured commit message from fields."""
    # Build title line
    prefix = "[UPDATE]" if is_update else ""
    title = f"{prefix}[{category}][{component}] {summary}"

    parts = [title, ""]

    # Impact projects section
    parts.append("[IMPACT PROJECTS]")
    parts.append(impact_projects)
    parts.append("")

    # Description section
    parts.append("[DESCRIPTION]")
    if commit_type == CommitType.BUGFIX:
        parts.append(f"BUG-ID: {bug_id or ''}")
        parts.append(f"SYMPTOM: {symptom or ''}")
        parts.append(f"ROOT CAUSE: {root_cause or ''}")
        parts.append(f"SOLUTION: {solution or ''}")
    else:
        parts.append(description or "")
    parts.append("")

    # Modified files section
    if modified_files:
        parts.append("modified:")
        for f in modified_files:
            parts.append(f)
        parts.append("")

    # Test section
    parts.append("[TEST]")
    parts.append(test)

    return "\n".join(parts)


def run_interactive_qa(
    *,
    modified_files: list[str],
    default_category: str | None = None,
    components: list[str] | None = None,
) -> dict:
    """Run interactive Q&A using click.prompt() and return collected fields."""
    comp_list = components if components is not None else DEFAULT_COMPONENTS

    # 1. New or update?
    init_or_update = click.prompt(
        "New or update?",
        type=click.Choice(["i", "u"], case_sensitive=False),
        prompt_suffix=" [i]nit / [u]pdate: ",
    )
    is_update = init_or_update.lower() == "u"

    # 2. Commit type
    type_choice = click.prompt(
        "Type?",
        type=click.Choice(["f", "b"], case_sensitive=False),
        prompt_suffix=" [f]eature / [b]ugfix: ",
    )
    commit_type = CommitType.FEATURE if type_choice.lower() == "f" else CommitType.BUGFIX

    # 3. Category
    category_kwargs: dict = {}
    if default_category:
        category_kwargs["default"] = default_category
    category = click.prompt(
        f"Category? ({'/'.join(CATEGORIES)})",
        **category_kwargs,
    )

    # 4. Component — show numbered list + 0 for custom
    comp_display = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(comp_list))
    comp_index_str = click.prompt(
        f"Component?\n{comp_display}\n  0. Custom\nEnter number (or 0 for custom)",
    )
    comp_index = int(comp_index_str)
    if comp_index == 0:
        component = click.prompt("Custom component name (uppercase)")
        component = component.upper()
    else:
        component = comp_list[comp_index - 1]

    # 5. Summary
    summary = click.prompt("Summary (one-line description)")

    # 6. Impact projects
    impact_projects = click.prompt("Impact projects/paths")

    # 7. Type-specific fields
    description: str | None = None
    bug_id: str | None = None
    symptom: str | None = None
    root_cause: str | None = None
    solution: str | None = None

    if commit_type == CommitType.BUGFIX:
        bug_id = click.prompt("Bug ID")
        symptom = click.prompt("Symptom")
        root_cause = click.prompt("Root cause")
        solution = click.prompt("Solution")
    else:
        description = click.prompt("Description (free-form)")

    # 8. Test
    test = click.prompt("Test description")

    return {
        "is_update": is_update,
        "commit_type": commit_type,
        "category": category,
        "component": component,
        "summary": summary,
        "impact_projects": impact_projects,
        "description": description,
        "bug_id": bug_id,
        "symptom": symptom,
        "root_cause": root_cause,
        "solution": solution,
        "test": test,
        "modified_files": modified_files,
    }
