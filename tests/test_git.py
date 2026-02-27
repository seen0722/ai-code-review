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


class TestGitError:
    def test_raises_when_not_in_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(GitError):
            get_staged_diff()
