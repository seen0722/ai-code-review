from ai_code_review.commit_check import check_commit_message, CommitCheckResult


class TestNewCommitMessageFormat:
    def test_valid_basic(self):
        result = check_commit_message("[BSP][CAMERA] fix null pointer crash")
        assert result.valid is True

    def test_valid_with_update(self):
        result = check_commit_message("[UPDATE][AP][NAL] update installation manager")
        assert result.valid is True

    def test_valid_cp_category(self):
        result = check_commit_message("[CP][AUDIO] add mixer path for headphone")
        assert result.valid is True

    def test_invalid_lowercase_component(self):
        result = check_commit_message("[BSP][camera] fix crash")
        assert result.valid is False

    def test_invalid_old_format(self):
        result = check_commit_message("[BSP-456] fix crash")
        assert result.valid is False

    def test_invalid_missing_component(self):
        result = check_commit_message("[BSP] fix crash")
        assert result.valid is False

    def test_invalid_wrong_category(self):
        result = check_commit_message("[QA][CAMERA] fix crash")
        assert result.valid is False

    def test_invalid_update_wrong_position(self):
        result = check_commit_message("[BSP][UPDATE][CAMERA] fix crash")
        assert result.valid is False

    def test_invalid_empty(self):
        result = check_commit_message("")
        assert result.valid is False

    def test_invalid_no_description(self):
        result = check_commit_message("[BSP][CAMERA]")
        assert result.valid is False

    def test_valid_update_lowercase_rejected(self):
        result = check_commit_message("[update][BSP][CAMERA] fix crash")
        assert result.valid is False

    def test_valid_multiline_checks_first_line(self):
        result = check_commit_message("[BSP][CAMERA] fix crash\n\nBody text here")
        assert result.valid is True
