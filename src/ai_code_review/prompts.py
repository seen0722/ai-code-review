from __future__ import annotations

_REVIEW_PROMPT = """\
You are a senior Android BSP engineer. Review the following git diff and report only serious issues.

Focus on:
- Memory leaks (malloc without free, unreleased resources)
- Null pointer dereference
- Race conditions, missing lock/mutex protection
- Hardcoded secrets (keys, passwords, tokens)
- Obvious logic errors
- Buffer overflow

Do not report:
- Code style or naming suggestions
- Performance optimization suggestions
- Refactoring suggestions

Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""

REVIEW_RESPONSE_SCHEMA = """Respond with a JSON array only. Each element:
{"severity": "critical|error|warning|info", "file": "path", "line": number, "message": "description"}
If no issues found, respond with []. No other text."""

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


_COT_GUIDANCE = """\
When reviewing, follow these steps:
1. Read the full file context to understand the complete function, struct definitions, and resource lifecycle
2. Check if the issue you found is already handled elsewhere in the file (cleanup functions, error paths, caller checks)
3. Only report an issue if you are confident it is a real problem based on the full context available
4. If the context is insufficient to confirm a problem, do not report it"""


def get_review_prompt(custom_rules: str | None = None) -> str:
    if not custom_rules:
        return _REVIEW_PROMPT
    return _REVIEW_PROMPT.replace(
        "\nDo not report:",
        f"\nAdditional rules:\n- {custom_rules}\n\nDo not report:",
    )


def get_review_prompt_with_context(
    file_contents: dict[str, str],
    custom_rules: str | None = None,
) -> str:
    if not file_contents:
        return get_review_prompt(custom_rules)
    base = get_review_prompt(custom_rules)
    respond_marker = "Respond with a JSON array only."
    cot_insertion = _COT_GUIDANCE + "\n\n"
    base = base.replace(respond_marker, cot_insertion + respond_marker, 1)
    file_section_parts = ["--- Full file context ---"]
    for filename, content in file_contents.items():
        file_section_parts.append(f"\n### {filename}\n```\n{content}\n```")
    base = base + "\n\n" + "\n".join(file_section_parts)
    return base


def get_commit_improve_prompt(message: str, diff: str) -> str:
    return _COMMIT_IMPROVE_PROMPT.format(message=message, diff=diff)


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
