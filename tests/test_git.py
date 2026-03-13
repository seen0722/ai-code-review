import subprocess
from unittest.mock import patch, call

import pytest

from ai_code_review.git import (
    get_staged_diff,
    get_unstaged_diff,
    get_commit_diff,
    get_push_diff,
    get_staged_file_contents,
    get_commit_file_contents,
    GitError,
)


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Create a temporary git repo with an initial commit."""
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestStagedDiff:
    def test_returns_staged_changes(self, git_repo):
        (git_repo / "file.c").write_text("int main() { return 0; }")
        subprocess.run(["git", "add", "file.c"], cwd=git_repo, check=True, capture_output=True)
        diff = get_staged_diff()
        assert "file.c" in diff
        assert "int main()" in diff

    def test_empty_when_nothing_staged(self, git_repo):
        diff = get_staged_diff()
        assert diff == ""

    def test_filters_by_extensions(self, git_repo):
        (git_repo / "main.c").write_text("int main() {}")
        (git_repo / "config.yaml").write_text("key: value")
        (git_repo / "util.h").write_text("void util();")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        diff = get_staged_diff(extensions=["c", "h"])
        assert "main.c" in diff
        assert "util.h" in diff
        assert "config.yaml" not in diff

    def test_extensions_empty_returns_all(self, git_repo):
        (git_repo / "main.c").write_text("int main() {}")
        (git_repo / "config.yaml").write_text("key: value")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        diff = get_staged_diff(extensions=None)
        assert "main.c" in diff
        assert "config.yaml" in diff

    def test_extensions_no_match_returns_empty(self, git_repo):
        (git_repo / "config.yaml").write_text("key: value")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        diff = get_staged_diff(extensions=["c", "cpp"])
        assert diff == ""


class TestUnstagedDiff:
    def test_returns_unstaged_changes(self, git_repo):
        (git_repo / "init.txt").write_text("modified")
        diff = get_unstaged_diff()
        assert "modified" in diff


class TestCommitDiff:
    def test_returns_diff_between_commits(self, git_repo):
        (git_repo / "new.c").write_text("void foo() {}")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=git_repo, check=True, capture_output=True)
        diff = get_commit_diff("HEAD~1", "HEAD")
        assert "new.c" in diff
        assert "void foo()" in diff


class TestCommitDiffExtensions:
    def test_filters_by_extensions(self, git_repo):
        """get_commit_diff with extensions only includes matching files."""
        (git_repo / "new.c").write_text("void foo() {}")
        (git_repo / "readme.md").write_text("# readme")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=git_repo, check=True, capture_output=True)
        diff = get_commit_diff("HEAD~1", "HEAD", extensions=["c"])
        assert "new.c" in diff
        assert "readme.md" not in diff

    def test_no_extensions_returns_all(self, git_repo):
        """get_commit_diff without extensions returns all files."""
        (git_repo / "new.c").write_text("void foo() {}")
        (git_repo / "readme.md").write_text("# readme")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=git_repo, check=True, capture_output=True)
        diff = get_commit_diff("HEAD~1", "HEAD")
        assert "new.c" in diff
        assert "readme.md" in diff


class TestGetPushDiff:
    def test_normal_push_returns_diff(self, git_repo):
        """Diff between two known SHAs."""
        sha1 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        # Create second commit
        (git_repo / "a.c").write_text("int x = 1;\n")
        subprocess.run(["git", "add", "a.c"], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=git_repo, check=True, capture_output=True)
        sha2 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        diff = get_push_diff(sha2, sha1)
        assert "int x = 1" in diff

    def test_normal_push_filters_extensions(self, git_repo):
        """Push diff respects extension filter."""
        sha1 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        (git_repo / "a.c").write_text("int x = 1;\n")
        (git_repo / "notes.txt").write_text("some notes\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=git_repo, check=True, capture_output=True)
        sha2 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        diff = get_push_diff(sha2, sha1, extensions=["c"])
        assert "a.c" in diff
        assert "notes.txt" not in diff

    def test_delete_branch_returns_empty(self):
        """Zero local SHA means branch deletion — returns empty."""
        zero_sha = "0" * 40
        diff = get_push_diff(zero_sha, "abc123")
        assert diff == ""

    def test_new_branch_no_remote_returns_empty(self, git_repo):
        """New branch with zero remote SHA and no remote refs returns empty."""
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        zero_sha = "0" * 40
        diff = get_push_diff(sha, zero_sha)
        # No remote, no main/master branch to diff against
        assert diff == ""

    def test_new_branch_with_local_main_returns_diff(self, git_repo):
        """New branch pushed when local 'main' exists — diffs from merge-base."""
        # Rename default branch to 'main' for this test
        subprocess.run(
            ["git", "branch", "-M", "main"], cwd=git_repo,
            check=True, capture_output=True,
        )
        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=git_repo, check=True, capture_output=True,
        )
        (git_repo / "feat.c").write_text("int feat = 1;\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat"], cwd=git_repo, check=True, capture_output=True)
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        zero_sha = "0" * 40
        diff = get_push_diff(sha, zero_sha)
        assert "feat.c" in diff
        assert "int feat = 1" in diff


class TestGitError:
    def test_raises_when_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(GitError):
            get_staged_diff()


class TestGetStagedFileContents:
    def test_returns_file_contents_for_staged_files(self):
        """Returns dict of filepath -> content for staged files."""
        def mock_run_git(*args):
            if args == ("diff", "--cached", "--name-only"):
                return "src/main.c\nsrc/util.h\n"
            if args == ("show", ":src/main.c"):
                return "int main() { return 0; }\n"
            if args == ("show", ":src/util.h"):
                return "void util();\n"
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            result = get_staged_file_contents()

        assert result == {
            "src/main.c": "int main() { return 0; }\n",
            "src/util.h": "void util();\n",
        }

    def test_filters_by_extension(self):
        """Only returns files matching the given extensions."""
        def mock_run_git(*args):
            if args == ("diff", "--cached", "--name-only"):
                return "main.c\nREADME.md\nutil.h\n"
            if args == ("show", ":main.c"):
                return "int main() {}\n"
            if args == ("show", ":util.h"):
                return "void util();\n"
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            result = get_staged_file_contents(extensions=["c", "h"])

        assert "main.c" in result
        assert "util.h" in result
        assert "README.md" not in result

    def test_returns_empty_when_no_staged_files(self):
        """Returns empty dict when nothing is staged."""
        with patch("ai_code_review.git._run_git", return_value=""):
            result = get_staged_file_contents()

        assert result == {}

    def test_respects_max_lines(self):
        """Stops adding files after max_lines exceeded, but always includes at least one."""
        big_content = "line\n" * 100  # 100 lines per file

        def mock_run_git(*args):
            if args == ("diff", "--cached", "--name-only"):
                return "a.c\nb.c\nc.c\n"
            if args[0] == "show":
                return big_content
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            # max_lines=100 — after a.c (100 lines) total equals limit, stops before b.c
            result = get_staged_file_contents(max_lines=100)

        assert "a.c" in result
        assert "b.c" not in result
        assert "c.c" not in result

    def test_always_includes_at_least_one_file(self):
        """Even if first file exceeds max_lines, it is still included."""
        big_content = "line\n" * 1000  # 1000 lines

        def mock_run_git(*args):
            if args == ("diff", "--cached", "--name-only"):
                return "big.c\nsmall.c\n"
            if args == ("show", ":big.c"):
                return big_content
            if args == ("show", ":small.c"):
                return "int x;\n"
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            result = get_staged_file_contents(max_lines=50)

        assert "big.c" in result
        assert "small.c" not in result

    def test_get_commit_file_contents(self):
        """Reads files at a specific commit SHA via git show sha:filepath."""
        sha = "abc1234"

        def mock_run_git(*args):
            if args == ("diff-tree", "--no-commit-id", "-r", "--name-only", sha):
                return "driver/foo.c\ndriver/bar.h\n"
            if args == ("show", f"{sha}:driver/foo.c"):
                return "static int foo() {}\n"
            if args == ("show", f"{sha}:driver/bar.h"):
                return "int bar;\n"
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            result = get_commit_file_contents(sha)

        assert result == {
            "driver/foo.c": "static int foo() {}\n",
            "driver/bar.h": "int bar;\n",
        }

    def test_get_commit_file_contents_filters_by_extension(self):
        """get_commit_file_contents respects extension filter."""
        sha = "deadbeef"

        def mock_run_git(*args):
            if args == ("diff-tree", "--no-commit-id", "-r", "--name-only", sha):
                return "main.c\nnotes.txt\n"
            if args == ("show", f"{sha}:main.c"):
                return "int main() {}\n"
            raise AssertionError(f"Unexpected _run_git call: {args}")

        with patch("ai_code_review.git._run_git", side_effect=mock_run_git):
            result = get_commit_file_contents(sha, extensions=["c"])

        assert "main.c" in result
        assert "notes.txt" not in result
