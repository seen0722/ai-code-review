import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ai_code_review.cli import main, _GLOBAL_HOOKS_DIR, _TEMPLATE_HOOKS_DIR


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
    def test_shows_all_three_sections(self, runner, git_repo):
        runner.invoke(main, ["hook", "install", "pre-commit"])
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "Template hooks" in result.output
        assert "Global hooks" in result.output
        assert "Current repo" in result.output
        assert "installed" in result.output.lower()

    def test_shows_not_installed(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower() or "not configured" in result.output.lower()


class TestHookStatusTemplate:
    def test_shows_template_status_when_configured(self, runner, git_repo, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        fake_template_dir.mkdir(parents=True)
        (fake_template_dir / "pre-commit").write_text("#!/bin/sh\nai-review")
        (fake_template_dir / "commit-msg").write_text("#!/bin/sh\nai-review check-commit")

        with patch("subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if "init.templateDir" in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=str(fake_template_dir.parent) + "\n")
                if "core.hooksPath" in cmd:
                    return subprocess.CompletedProcess(cmd, 1, stdout="")
                if "ai-review.enabled" in cmd:
                    return subprocess.CompletedProcess(cmd, 1, stdout="")
                return subprocess.CompletedProcess(cmd, 0, stdout="")
            mock_run.side_effect = side_effect
            result = runner.invoke(main, ["hook", "status"])

        assert result.exit_code == 0
        assert "Template hooks" in result.output
        assert "init.templateDir" in result.output

    def test_shows_enabled_status(self, runner, git_repo):
        subprocess.run(
            ["git", "config", "--local", "ai-review.enabled", "true"],
            cwd=git_repo, check=True,
        )
        result = runner.invoke(main, ["hook", "status"])
        assert result.exit_code == 0
        assert "ai-review.enabled = true" in result.output


class TestTemplateHookScripts:
    def test_template_scripts_use_git_config_opt_in(self):
        from ai_code_review.cli import _generate_template_hook_scripts
        scripts = _generate_template_hook_scripts()
        for hook_type in ["pre-commit", "commit-msg"]:
            script = scripts[hook_type]
            assert "git config --local ai-review.enabled" in script
            assert ".ai-review" not in script
            assert "ai-review" in script

    def test_template_scripts_are_different_from_global(self):
        from ai_code_review.cli import _generate_hook_scripts, _generate_template_hook_scripts
        global_scripts = _generate_hook_scripts()
        template_scripts = _generate_template_hook_scripts()
        assert global_scripts["pre-commit"] != template_scripts["pre-commit"]


class TestTemplateHookInstall:
    def test_installs_template_hooks(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "install", "--template"])

        assert result.exit_code == 0
        assert (fake_template_dir / "pre-commit").exists()
        assert (fake_template_dir / "commit-msg").exists()
        assert "git config --local ai-review.enabled" in (fake_template_dir / "pre-commit").read_text()
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "init.templateDir",
             str(fake_template_dir.parent)],
            check=True,
        )

    def test_template_hook_scripts_are_executable(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run"):
            runner.invoke(main, ["hook", "install", "--template"])

        for hook_type in ["pre-commit", "commit-msg"]:
            hook_path = fake_template_dir / hook_type
            assert hook_path.stat().st_mode & 0o755


class TestTemplateHookUninstall:
    def test_uninstalls_template_hooks(self, runner, tmp_path):
        fake_template_dir = tmp_path / "template" / "hooks"
        fake_template_dir.mkdir(parents=True)
        (fake_template_dir / "pre-commit").write_text("#!/bin/sh\nai-review")
        (fake_template_dir / "commit-msg").write_text("#!/bin/sh\nai-review check-commit")

        with patch("ai_code_review.cli._TEMPLATE_HOOKS_DIR", fake_template_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            result = runner.invoke(main, ["hook", "uninstall", "--template"])

        assert result.exit_code == 0
        assert not (fake_template_dir / "pre-commit").exists()
        assert not (fake_template_dir / "commit-msg").exists()
        mock_run.assert_called_once_with(
            ["git", "config", "--global", "--unset", "init.templateDir"],
            check=True, capture_output=True,
        )


class TestHookEnableDisable:
    def test_enable_sets_git_config(self, runner, git_repo):
        result = runner.invoke(main, ["hook", "enable"])
        assert result.exit_code == 0
        config_result = subprocess.run(
            ["git", "config", "--local", "ai-review.enabled"],
            capture_output=True, text=True, cwd=git_repo,
        )
        assert config_result.stdout.strip() == "true"

    def test_disable_unsets_git_config(self, runner, git_repo):
        subprocess.run(
            ["git", "config", "--local", "ai-review.enabled", "true"],
            cwd=git_repo, check=True,
        )
        result = runner.invoke(main, ["hook", "disable"])
        assert result.exit_code == 0
        config_result = subprocess.run(
            ["git", "config", "--local", "ai-review.enabled"],
            capture_output=True, text=True, cwd=git_repo,
        )
        assert config_result.returncode != 0

    def test_enable_not_in_git_repo(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["hook", "enable"])
        assert result.exit_code != 0
