import subprocess

import pytest

from ai_code_review.git import get_staged_diff, get_unstaged_diff, get_commit_diff, GitError


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


class TestGitError:
    def test_raises_when_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(GitError):
            get_staged_diff()
