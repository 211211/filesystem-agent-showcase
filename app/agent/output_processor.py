"""Output processor for truncating long tool outputs."""

from dataclasses import dataclass


@dataclass
class TruncationResult:
    """Result of output truncation."""
    content: str
    was_truncated: bool
    original_lines: int
    original_chars: int


class OutputProcessor:
    """Process and truncate tool outputs to save tokens.

    IMPORTANT: The default limits are set to 200 lines / 50000 chars to avoid
    triggering retry loops. When output shows "[OUTPUT TRUNCATED]", the LLM
    often makes MORE tool calls to get complete data, which INCREASES tokens.

    Original defaults (50 lines) caused 200%+ token INCREASE in benchmarks.
    These larger defaults provide ~57% token REDUCTION while still limiting
    extremely large outputs.
    """

    # CORRECTED DEFAULTS - larger limits to avoid retry loops
    # See benchmarks/token_usage_comparison_v2.py for analysis
    DEFAULT_MAX_LINES = 200
    DEFAULT_MAX_CHARS = 50000

    def __init__(
        self,
        max_lines: int = DEFAULT_MAX_LINES,
        max_chars: int = DEFAULT_MAX_CHARS
    ):
        self.max_lines = max_lines
        self.max_chars = max_chars

    def truncate(self, output: str) -> TruncationResult:
        """Truncate output if it exceeds limits.

        Args:
            output: Raw command output

        Returns:
            TruncationResult with possibly truncated content
        """
        lines = output.split('\n')
        total_lines = len(lines)
        total_chars = len(output)

        # Check if truncation needed
        if total_lines <= self.max_lines and total_chars <= self.max_chars:
            return TruncationResult(
                content=output,
                was_truncated=False,
                original_lines=total_lines,
                original_chars=total_chars
            )

        # Truncate by lines first
        truncated_lines = lines[:self.max_lines]
        truncated = '\n'.join(truncated_lines)

        # Then by chars if still too long
        if len(truncated) > self.max_chars:
            truncated = truncated[:self.max_chars]

        # Add metadata footer - NOTE: Don't suggest more tools to avoid retry loops
        remaining_lines = total_lines - self.max_lines
        content = f"""[OUTPUT TRUNCATED: Showing {self.max_lines}/{total_lines} lines]

{truncated}

[... {remaining_lines} more lines omitted for brevity ...]"""

        return TruncationResult(
            content=content,
            was_truncated=True,
            original_lines=total_lines,
            original_chars=total_chars
        )

    def process(self, output: str) -> str:
        """Process output and return string (convenience method)."""
        return self.truncate(output).content


# Default singleton instance
default_processor = OutputProcessor()


def truncate_output(output: str, max_lines: int = 200, max_chars: int = 50000) -> str:
    """Convenience function for truncating output."""
    processor = OutputProcessor(max_lines=max_lines, max_chars=max_chars)
    return processor.process(output)
