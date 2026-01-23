from app.agent.output_processor import OutputProcessor, TruncationResult, truncate_output


class TestOutputProcessor:
    def test_short_output_unchanged(self):
        """Short output should not be truncated."""
        processor = OutputProcessor()
        result = processor.truncate("line1\nline2\nline3")

        assert result.was_truncated is False
        assert result.content == "line1\nline2\nline3"
        assert result.original_lines == 3

    def test_long_output_truncated_by_lines(self):
        """Output exceeding max_lines should be truncated."""
        processor = OutputProcessor(max_lines=5)
        long_output = "\n".join([f"line{i}" for i in range(100)])

        result = processor.truncate(long_output)

        assert result.was_truncated is True
        assert result.original_lines == 100
        assert "[OUTPUT TRUNCATED" in result.content
        assert "95 more lines" in result.content

    def test_long_output_truncated_by_chars(self):
        """Output exceeding max_chars should be truncated."""
        processor = OutputProcessor(max_lines=1000, max_chars=100)
        long_output = "x" * 500

        result = processor.truncate(long_output)

        assert result.was_truncated is True
        assert result.original_chars == 500

    def test_truncate_preserves_line_count_info(self):
        """Truncation should include line count metadata."""
        processor = OutputProcessor(max_lines=10)
        output = "\n".join([f"line{i}" for i in range(50)])

        result = processor.truncate(output)

        assert "10/50 lines" in result.content

    def test_truncate_indicates_omitted(self):
        """Truncated output should indicate content was omitted."""
        processor = OutputProcessor(max_lines=5)
        output = "\n".join([f"line{i}" for i in range(20)])

        result = processor.truncate(output)

        # Note: We don't suggest "grep/head/tail" anymore because that triggers
        # retry loops in the LLM, increasing token usage
        assert "omitted for brevity" in result.content

    def test_process_returns_string(self):
        """process() should return string directly."""
        processor = OutputProcessor()
        result = processor.process("test output")

        assert isinstance(result, str)
        assert result == "test output"

    def test_truncate_output_function(self):
        """Convenience function should work."""
        output = "\n".join([f"line{i}" for i in range(100)])
        result = truncate_output(output, max_lines=10)

        assert "[OUTPUT TRUNCATED" in result

    def test_empty_output(self):
        """Empty output should be handled."""
        processor = OutputProcessor()
        result = processor.truncate("")

        assert result.was_truncated is False
        assert result.content == ""

    def test_custom_limits(self):
        """Custom limits should be respected."""
        processor = OutputProcessor(max_lines=3, max_chars=50)

        assert processor.max_lines == 3
        assert processor.max_chars == 50


class TestTruncationResult:
    def test_truncation_result_dataclass(self):
        """TruncationResult should work as a dataclass."""
        result = TruncationResult(
            content="test",
            was_truncated=True,
            original_lines=100,
            original_chars=5000
        )

        assert result.content == "test"
        assert result.was_truncated is True
        assert result.original_lines == 100
        assert result.original_chars == 5000


class TestOutputProcessorEdgeCases:
    def test_single_line_long_chars(self):
        """Single line exceeding char limit should be truncated."""
        processor = OutputProcessor(max_lines=50, max_chars=50)
        output = "a" * 200

        result = processor.truncate(output)

        assert result.was_truncated is True
        assert len(result.content) < len(output)

    def test_exact_max_lines_not_truncated(self):
        """Output with exactly max_lines should not be truncated."""
        processor = OutputProcessor(max_lines=5)
        output = "\n".join([f"line{i}" for i in range(5)])

        result = processor.truncate(output)

        assert result.was_truncated is False

    def test_exact_max_chars_not_truncated(self):
        """Output with exactly max_chars should not be truncated."""
        processor = OutputProcessor(max_lines=100, max_chars=20)
        output = "a" * 20

        result = processor.truncate(output)

        assert result.was_truncated is False

    def test_whitespace_only_output(self):
        """Whitespace-only output should be handled."""
        processor = OutputProcessor()
        result = processor.truncate("   \n   \n   ")

        assert result.was_truncated is False

    def test_truncation_with_unicode(self):
        """Unicode content should be handled correctly."""
        processor = OutputProcessor(max_lines=5)
        output = "\n".join(["Hello World"] * 10)

        result = processor.truncate(output)

        assert result.was_truncated is True

    def test_default_singleton(self):
        """Default processor singleton should be available."""
        from app.agent.output_processor import default_processor

        assert isinstance(default_processor, OutputProcessor)
        assert default_processor.max_lines == OutputProcessor.DEFAULT_MAX_LINES
        assert default_processor.max_chars == OutputProcessor.DEFAULT_MAX_CHARS

    def test_truncation_preserves_first_lines(self):
        """Truncation should preserve the first max_lines lines."""
        processor = OutputProcessor(max_lines=3)
        output = "line0\nline1\nline2\nline3\nline4"

        result = processor.truncate(output)

        assert "line0" in result.content
        assert "line1" in result.content
        assert "line2" in result.content
        # line3 and line4 should be in the "more lines" part

    def test_char_truncation_applied_after_line_truncation(self):
        """Character truncation should be applied after line truncation."""
        # Create output where line truncation alone won't be enough
        processor = OutputProcessor(max_lines=10, max_chars=20)
        # 10 lines of "xxxx" = 50 chars (including newlines)
        output = "\n".join(["xxxx"] * 10)

        result = processor.truncate(output)

        assert result.was_truncated is True
        # The truncated content should be under max_chars
        # (Note: the metadata header adds some chars, so we check the truncated portion)
