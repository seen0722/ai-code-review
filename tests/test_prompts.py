from ai_code_review.prompts import get_review_prompt, get_commit_improve_prompt, get_generate_commit_prompt


class TestReviewPrompt:
    def test_contains_bsp_focus_areas(self):
        prompt = get_review_prompt()
        assert "memory leak" in prompt.lower()
        assert "null pointer" in prompt.lower()
        assert "race condition" in prompt.lower()

    def test_excludes_style_review(self):
        prompt = get_review_prompt()
        assert "naming" not in prompt.lower() or "do not" in prompt.lower()


    def test_no_custom_rules_returns_default(self):
        prompt = get_review_prompt()
        assert "Additional rules" not in prompt

    def test_custom_rules_appended(self):
        prompt = get_review_prompt("check integer overflow")
        assert "Additional rules:" in prompt
        assert "check integer overflow" in prompt

    def test_custom_rules_before_do_not_report(self):
        prompt = get_review_prompt("check use-after-free")
        do_not_pos = prompt.index("Do not report:")
        rules_pos = prompt.index("Additional rules:")
        assert rules_pos < do_not_pos

    def test_none_custom_rules_returns_default(self):
        prompt = get_review_prompt(None)
        assert "Additional rules" not in prompt

    def test_empty_string_custom_rules_returns_default(self):
        prompt = get_review_prompt("")
        assert "Additional rules" not in prompt


class TestCommitImprovePrompt:
    def test_contains_grammar_instruction(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "diff content")
        assert "grammar" in prompt.lower()

    def test_contains_original_message(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "diff content")
        assert "[BSP-1] fix bug" in prompt

    def test_contains_diff(self):
        prompt = get_commit_improve_prompt("[BSP-1] fix bug", "some diff here")
        assert "some diff here" in prompt


class TestGenerateCommitPrompt:
    def test_prompt_contains_diff(self):
        prompt = get_generate_commit_prompt("+ int x = 0;")
        assert "+ int x = 0;" in prompt

    def test_prompt_instructs_imperative_mood(self):
        prompt = get_generate_commit_prompt("some diff")
        assert "imperative" in prompt.lower()

    def test_prompt_instructs_concise(self):
        prompt = get_generate_commit_prompt("some diff")
        assert "72" in prompt
