import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestHookInstall:
    def test_installs_pre_commit_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "pre-commit"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists()
        assert "ai-review" in hook_path.read_text()

    def test_installs_commit_msg_hook(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "install", "commit-msg"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "commit-msg"
        assert hook_path.exists()
        assert "ai-review" in hook_path.read_text()


class TestHookUninstall:
    def test_removes_hook(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "uninstall", "pre-commit"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        assert not hook_path.exists()


class TestHookStatus:
    def test_shows_installed_hooks(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "pre-commit" in result.output
        assert "installed" in result.output.lower()
