import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main, _GLOBAL_HOOKS_DIR


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


class TestRepoHookInstall:
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
        assert "--auto-accept" in hook_path.read_text()


class TestRepoHookUninstall:
    def test_removes_hook(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "uninstall", "pre-commit"])
        assert result.exit_code == 0
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        assert not hook_path.exists()


class TestGlobalHookInstall:
    def test_installs_global_hooks(self, runner, tmp_path):
        fake_hooks_dir = tmp_path / "global-hooks"
        with patch("ai_code_review.cli._GLOBAL_HOOKS_DIR", fake_hooks_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "install", "--global"])

        assert result.exit_code == 0
        assert (fake_hooks_dir / "pre-commit").exists()
        assert (fake_hooks_dir / "commit-msg").exists()
        assert "ai-review" in (fake_hooks_dir / "pre-commit").read_text()
        assert "ai-review" in (fake_hooks_dir / "commit-msg").read_text()
        # Verify git config --global was called
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "core.hooksPath", str(fake_hooks_dir)],
            check=True,
        )

    def test_hook_scripts_are_executable(self, runner, tmp_path):
        fake_hooks_dir = tmp_path / "global-hooks"
        with patch("ai_code_review.cli._GLOBAL_HOOKS_DIR", fake_hooks_dir), \
             patch("subprocess.run"):
            runner.invoke(main, ["hook", "install", "--global"])

        for hook_type in ["pre-commit", "commit-msg"]:
            hook_path = fake_hooks_dir / hook_type
            assert hook_path.stat().st_mode & 0o755


class TestGlobalHookUninstall:
    def test_uninstalls_global_hooks(self, runner, tmp_path):
        fake_hooks_dir = tmp_path / "global-hooks"
        fake_hooks_dir.mkdir(parents=True)
        (fake_hooks_dir / "pre-commit").write_text("#!/bin/sh\nai-review")
        (fake_hooks_dir / "commit-msg").write_text("#!/bin/sh\nai-review check-commit")

        with patch("ai_code_review.cli._GLOBAL_HOOKS_DIR", fake_hooks_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "uninstall", "--global"])

        assert result.exit_code == 0
        assert not (fake_hooks_dir / "pre-commit").exists()
        assert not (fake_hooks_dir / "commit-msg").exists()
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "--unset", "core.hooksPath"],
            check=True, capture_output=True,
        )


class TestHookStatus:
    def test_shows_global_and_repo_status(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "Global hooks" in result.output
        assert "Current repo hooks" in result.output
        assert "installed" in result.output.lower()

    def test_shows_not_installed(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower() or "not configured" in result.output.lower()
