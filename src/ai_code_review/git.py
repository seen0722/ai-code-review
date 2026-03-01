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
