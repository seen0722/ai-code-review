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


def get_commit_diff(from_ref: str, to_ref: str) -> str:
    return _run_git("diff", from_ref, to_ref).strip()
