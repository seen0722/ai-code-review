from __future__ import annotations

import subprocess


class GitError(Exception):
    pass


def _run_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        raise GitError("git is not installed or not in PATH")
    return result.stdout


def get_staged_diff(extensions: list[str] | None = None) -> str:
    args = ["diff", "--cached"]
    if extensions:
        args.append("--")
        args.extend(f"*.{ext.lstrip('.')}" for ext in extensions)
    return _run_git(*args).strip()


def get_unstaged_diff() -> str:
    return _run_git("diff").strip()


def get_commit_diff(from_ref: str, to_ref: str, extensions: list[str] | None = None) -> str:
    args = ["diff", from_ref, to_ref]
    if extensions:
        args.append("--")
        args.extend(f"*.{ext.lstrip('.')}" for ext in extensions)
    return _run_git(*args).strip()


_ZERO_SHA = "0" * 40


def _get_file_contents(
    file_list_cmd: list[str],
    show_prefix: str,
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Read file contents from git for a list of files.

    Args:
        file_list_cmd: git sub-command args to get the list of file paths.
        show_prefix: prefix for ``git show`` (e.g. ``":"`` for staged, ``"sha:"`` for a commit).
        extensions: optional list of extensions to include (without leading dot).
        max_lines: stop adding more files once the total line count exceeds this
                   value. At least one file is always included.

    Returns:
        A dict mapping filepath to file content.
    """
    raw = _run_git(*file_list_cmd)
    filepaths = [p for p in raw.splitlines() if p]
    if extensions:
        norm = {ext.lstrip(".") for ext in extensions}
        filepaths = [p for p in filepaths if p.rsplit(".", 1)[-1] in norm]

    result: dict[str, str] = {}
    total_lines = 0
    for filepath in filepaths:
        content = _run_git("show", f"{show_prefix}{filepath}")
        result[filepath] = content
        total_lines += content.count("\n")
        if total_lines >= max_lines:
            break
    return result


def get_staged_file_contents(
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Return the full contents of staged files.

    Args:
        extensions: optional list of file extensions to include (e.g. ``["c", "h"]``).
        max_lines: stop adding more files once the total line count exceeds this value.

    Returns:
        A dict mapping filepath to file content.
    """
    return _get_file_contents(
        ["diff", "--cached", "--name-only"],
        ":",
        extensions=extensions,
        max_lines=max_lines,
    )


def get_commit_file_contents(
    commit_sha: str,
    extensions: list[str] | None = None,
    max_lines: int = 5000,
) -> dict[str, str]:
    """Return the full contents of files changed in a specific commit.

    Args:
        commit_sha: the commit SHA to inspect.
        extensions: optional list of file extensions to include.
        max_lines: stop adding more files once the total line count exceeds this value.

    Returns:
        A dict mapping filepath to file content.
    """
    return _get_file_contents(
        ["diff-tree", "--no-commit-id", "-r", "--name-only", commit_sha],
        f"{commit_sha}:",
        extensions=extensions,
        max_lines=max_lines,
    )


def get_push_diff(local_sha: str, remote_sha: str, extensions: list[str] | None = None) -> str:
    """Get diff for commits being pushed.

    Args:
        local_sha: The local commit SHA being pushed.
        remote_sha: The remote commit SHA (current tip of the remote branch).
        extensions: Optional list of file extensions to filter the diff.

    Returns:
        The diff string, or empty string if the branch is being deleted
        or no base can be determined.
    """
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
