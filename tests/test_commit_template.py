from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_code_review.commit_template import (
    CATEGORIES,
    DEFAULT_COMPONENTS,
    CommitType,
    build_commit_message,
    run_interactive_qa,
)


class TestBuildCommitMessage:
    def test_feature_message(self):
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="CAMERA",
            summary="add HDR support",
            commit_type=CommitType.FEATURE,
            impact_projects="device/vendor/camera",
            description="Implement HDR pipeline in camera HAL",
            test="Boot device, open camera, verify HDR toggle",
            modified_files=["hal/camera.c", "hal/camera.h"],
        )
        assert msg.startswith("[BSP][CAMERA] add HDR support")
        assert "[IMPACT PROJECTS]" in msg
        assert "device/vendor/camera" in msg
        assert "[DESCRIPTION]" in msg
        assert "Implement HDR pipeline in camera HAL" in msg
        assert "modified:" in msg
        assert "hal/camera.c" in msg
        assert "hal/camera.h" in msg
        assert "[TEST]" in msg
        assert "Boot device, open camera, verify HDR toggle" in msg

    def test_bugfix_message(self):
        msg = build_commit_message(
            is_update=False,
            category="CP",
            component="AUDIO",
            summary="fix audio underrun on playback",
            commit_type=CommitType.BUGFIX,
            impact_projects="device/vendor/audio",
            test="Play music for 10 minutes, verify no underrun",
            modified_files=["audio/pcm.c"],
            bug_id="BSP-1234",
            symptom="Audio drops during playback",
            root_cause="Buffer size too small",
            solution="Increase PCM buffer to 4096 bytes",
        )
        assert msg.startswith("[CP][AUDIO] fix audio underrun on playback")
        assert "[DESCRIPTION]" in msg
        assert "BUG-ID: BSP-1234" in msg
        assert "SYMPTOM: Audio drops during playback" in msg
        assert "ROOT CAUSE: Buffer size too small" in msg
        assert "SOLUTION: Increase PCM buffer to 4096 bytes" in msg
        assert "modified:" in msg
        assert "audio/pcm.c" in msg
        assert "[TEST]" in msg

    def test_update_prefix(self):
        msg = build_commit_message(
            is_update=True,
            category="AP",
            component="DISPLAY",
            summary="update brightness curve",
            commit_type=CommitType.FEATURE,
            impact_projects="device/vendor/display",
            description="Tune brightness",
            test="Check display brightness",
            modified_files=[],
        )
        assert msg.startswith("[UPDATE][AP][DISPLAY] update brightness curve")

    def test_no_update_prefix(self):
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="POWER",
            summary="add suspend mode",
            commit_type=CommitType.FEATURE,
            impact_projects="device/vendor/power",
            description="Add deep suspend",
            test="Suspend and resume device",
            modified_files=[],
        )
        assert "[UPDATE]" not in msg
        assert msg.startswith("[BSP][POWER] add suspend mode")

    def test_empty_modified_files(self):
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="SENSOR",
            summary="fix sensor init",
            commit_type=CommitType.FEATURE,
            impact_projects="device/vendor/sensor",
            description="Fix init sequence",
            test="Boot and check sensor",
            modified_files=[],
        )
        # modified: section should still appear (or be absent gracefully)
        assert "[TEST]" in msg

    def test_bugfix_none_fields(self):
        # bugfix with None optional fields — should not crash
        msg = build_commit_message(
            is_update=False,
            category="BSP",
            component="MEMORY",
            summary="fix memory leak",
            commit_type=CommitType.BUGFIX,
            impact_projects="device/vendor/mem",
            test="Run valgrind",
            modified_files=["mem.c"],
            bug_id=None,
            symptom=None,
            root_cause=None,
            solution=None,
        )
        assert "[DESCRIPTION]" in msg
        assert "[TEST]" in msg


class TestCategories:
    def test_valid_categories(self):
        assert "BSP" in CATEGORIES
        assert "CP" in CATEGORIES
        assert "AP" in CATEGORIES
        assert len(CATEGORIES) == 3

    def test_default_components_non_empty(self):
        assert len(DEFAULT_COMPONENTS) > 0
        for comp in DEFAULT_COMPONENTS:
            assert comp == comp.upper()


class TestRunInteractiveQa:
    def test_feature_flow(self):
        # Inputs: init, feature, BSP, CAMERA (index 1), summary, impact, description, test
        inputs = iter([
            "i",        # new or update
            "f",        # feature
            "BSP",      # category
            "1",        # component index (CAMERA)
            "add HDR",  # summary
            "device/vendor/camera",  # impact projects
            "Implement HDR",         # description
            "test HDR",              # test
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=["hal/camera.c"],
                default_category=None,
                components=None,
            )
        assert result["is_update"] is False
        assert result["commit_type"] == CommitType.FEATURE
        assert result["category"] == "BSP"
        assert result["component"] == DEFAULT_COMPONENTS[0]  # index 1 -> first component
        assert result["summary"] == "add HDR"
        assert result["impact_projects"] == "device/vendor/camera"
        assert result["description"] == "Implement HDR"
        assert result["test"] == "test HDR"
        assert result["modified_files"] == ["hal/camera.c"]

    def test_bugfix_flow(self):
        # Inputs: init, bugfix, CP, AUDIO (index 2), summary, impact, bug_id, symptom, root_cause, solution, test
        inputs = iter([
            "i",        # new or update
            "b",        # bugfix
            "CP",       # category
            "2",        # component index (AUDIO)
            "fix audio",# summary
            "device/audio",  # impact projects
            "BSP-999",  # bug id
            "audio drop",    # symptom
            "small buffer",  # root cause
            "increase buffer", # solution
            "play music",    # test
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=["audio/pcm.c"],
                default_category=None,
                components=None,
            )
        assert result["is_update"] is False
        assert result["commit_type"] == CommitType.BUGFIX
        assert result["category"] == "CP"
        assert result["component"] == DEFAULT_COMPONENTS[1]  # index 2 -> second component
        assert result["summary"] == "fix audio"
        assert result["bug_id"] == "BSP-999"
        assert result["symptom"] == "audio drop"
        assert result["root_cause"] == "small buffer"
        assert result["solution"] == "increase buffer"
        assert result["test"] == "play music"
        assert result["description"] is None

    def test_update_flow(self):
        inputs = iter([
            "u",        # update
            "f",        # feature
            "AP",       # category
            "1",        # component index
            "update brightness",  # summary
            "device/display",     # impact projects
            "tune curve",         # description
            "check display",      # test
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=[],
                default_category=None,
                components=None,
            )
        assert result["is_update"] is True
        assert result["commit_type"] == CommitType.FEATURE
        assert result["category"] == "AP"

    def test_custom_component(self):
        # User picks "0" for custom component, then types the name
        inputs = iter([
            "i",        # new or update
            "f",        # feature
            "BSP",      # category
            "0",        # custom component
            "WIFI",     # custom component name
            "add wifi",  # summary
            "device/wifi",  # impact
            "enable wifi",  # description
            "test wifi",    # test
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=[],
                default_category=None,
                components=None,
            )
        assert result["component"] == "WIFI"

    def test_default_category_used(self):
        # default_category is pre-filled — category prompt should use it
        inputs = iter([
            "i",        # new or update
            "f",        # feature
            "BSP",      # category (even though default provided, still prompted)
            "1",        # component
            "summary",
            "impact",
            "desc",
            "test",
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=[],
                default_category="BSP",
                components=None,
            )
        assert result["category"] == "BSP"

    def test_custom_components_list(self):
        # When components list is provided, use that instead of DEFAULT_COMPONENTS
        custom_comps = ["WIFI", "BT", "NFC"]
        inputs = iter([
            "i",
            "f",
            "BSP",
            "2",        # index 2 -> BT
            "fix bt",
            "device/bt",
            "enable bt",
            "test bt",
        ])
        with patch("click.prompt", side_effect=inputs):
            result = run_interactive_qa(
                modified_files=[],
                default_category=None,
                components=custom_comps,
            )
        assert result["component"] == "BT"  # index 2 -> second item
