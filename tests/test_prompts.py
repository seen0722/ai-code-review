from ai_code_review.prompts import get_review_prompt, get_commit_improve_prompt, get_generate_commit_prompt, get_review_prompt_with_context, get_commit_polish_prompt


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


class TestReviewPromptWithContext:
    def test_includes_cot_guidance(self):
        prompt = get_review_prompt_with_context({"foo.c": "int main() {}"})
        assert "follow these steps" in prompt
        assert "confident it is a real problem" in prompt

    def test_includes_file_contents(self):
        prompt = get_review_prompt_with_context({"driver/foo.c": "int x = 0;"})
        assert "driver/foo.c" in prompt
        assert "int x = 0;" in prompt

    def test_includes_custom_rules(self):
        prompt = get_review_prompt_with_context(
            {"foo.c": "int x;"}, custom_rules="check integer overflow"
        )
        assert "Additional rules:" in prompt
        assert "check integer overflow" in prompt

    def test_empty_file_contents_returns_basic_prompt(self):
        prompt = get_review_prompt_with_context({})
        assert "follow these steps" not in prompt
        assert "Full file context" not in prompt
        assert prompt == get_review_prompt()


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


class TestCommitPolishPrompt:
    def test_includes_user_fields_and_diff(self):
        prompt = get_commit_polish_prompt("fix crash", "null ptr in camera", "diff content")
        assert "fix crash" in prompt
        assert "null ptr in camera" in prompt
        assert "diff content" in prompt

    def test_includes_summary_label(self):
        prompt = get_commit_polish_prompt("fix crash", "desc", "diff")
        assert "User summary:" in prompt

    def test_includes_description_label(self):
        prompt = get_commit_polish_prompt("fix crash", "desc", "diff")
        assert "User description:" in prompt

    def test_instructs_grammar_fix(self):
        prompt = get_commit_polish_prompt("fix crash", "desc", "diff")
        assert "grammar" in prompt.lower()

    def test_instructs_72_char_limit(self):
        prompt = get_commit_polish_prompt("fix crash", "desc", "diff")
        assert "72" in prompt

    def test_specifies_output_format(self):
        prompt = get_commit_polish_prompt("fix crash", "desc", "diff")
        assert "SUMMARY:" in prompt
        assert "DESCRIPTION:" in prompt
