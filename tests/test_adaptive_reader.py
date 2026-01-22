"""
Tests for the adaptive file reader module.
"""

import pytest
from pathlib import Path
import tempfile

from app.sandbox.executor import SandboxExecutor
from app.agent.tools.adaptive_reader import AdaptiveFileReader


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir).resolve()
        yield test_dir


@pytest.fixture
def sandbox(temp_dir):
    """Create a sandbox executor for testing."""
    return SandboxExecutor(root_path=temp_dir, timeout=10, enabled=True)


@pytest.fixture
def adaptive_reader(sandbox):
    """Create an AdaptiveFileReader instance with small thresholds for testing."""
    return AdaptiveFileReader(
        sandbox=sandbox,
        small_threshold=500,     # 500 bytes for testing
        medium_threshold=2000    # 2KB for testing
    )


@pytest.fixture
def small_file(temp_dir):
    """Create a small file (< 500 bytes)."""
    file_path = temp_dir / "small.txt"
    content = "Line 1\nLine 2\nLine 3\n"  # ~21 bytes
    file_path.write_text(content)
    return file_path


@pytest.fixture
def medium_file(temp_dir):
    """Create a medium file (500 bytes - 2KB)."""
    file_path = temp_dir / "medium.txt"
    # Create a file of ~1KB
    lines = [f"Line {i}: This is medium file content\n" for i in range(1, 30)]
    file_path.write_text("".join(lines))
    return file_path


@pytest.fixture
def large_file(temp_dir):
    """Create a large file (> 2KB)."""
    file_path = temp_dir / "large.txt"
    # Create a file of ~5KB
    lines = [f"Line {i}: This is large file content with more text to make it bigger\n" for i in range(1, 100)]
    file_path.write_text("".join(lines))
    return file_path


@pytest.fixture
def searchable_file(temp_dir):
    """Create a medium file with searchable content."""
    file_path = temp_dir / "searchable.txt"
    lines = []
    for i in range(1, 50):
        if i % 5 == 0:
            lines.append(f"Line {i}: PATTERN_MATCH here\n")
        else:
            lines.append(f"Line {i}: Regular content\n")
    file_path.write_text("".join(lines))
    return file_path


class TestAdaptiveFileReaderInit:
    """Tests for AdaptiveFileReader initialization."""

    def test_default_thresholds(self, sandbox):
        """Test default threshold values."""
        reader = AdaptiveFileReader(sandbox=sandbox)
        assert reader.small_threshold == 1_000_000
        assert reader.medium_threshold == 100_000_000

    def test_custom_thresholds(self, sandbox):
        """Test custom threshold values."""
        reader = AdaptiveFileReader(
            sandbox=sandbox,
            small_threshold=100,
            medium_threshold=1000
        )
        assert reader.small_threshold == 100
        assert reader.medium_threshold == 1000


class TestStrategySelection:
    """Tests for strategy selection logic."""

    def test_small_file_strategy(self, adaptive_reader):
        """Test that small files use full_read strategy."""
        strategy = adaptive_reader._select_strategy(100, query=None)
        assert strategy == "full_read"

    def test_medium_file_with_query_strategy(self, adaptive_reader):
        """Test that medium files with query use grep strategy."""
        strategy = adaptive_reader._select_strategy(1000, query="pattern")
        assert strategy == "grep"

    def test_medium_file_without_query_strategy(self, adaptive_reader):
        """Test that medium files without query use head_tail strategy."""
        strategy = adaptive_reader._select_strategy(1000, query=None)
        assert strategy == "head_tail"

    def test_large_file_strategy(self, adaptive_reader):
        """Test that large files use head_tail strategy."""
        strategy = adaptive_reader._select_strategy(5000, query=None)
        assert strategy == "head_tail"

    def test_large_file_with_query_strategy(self, adaptive_reader):
        """Test that large files use head_tail even with query."""
        strategy = adaptive_reader._select_strategy(5000, query="pattern")
        assert strategy == "head_tail"


class TestSmartReadFullRead:
    """Tests for smart_read with full_read strategy."""

    @pytest.mark.asyncio
    async def test_full_read_small_file(self, adaptive_reader, small_file):
        """Test reading a small file entirely."""
        result = await adaptive_reader.smart_read(small_file)

        assert result["strategy"] == "full_read"
        assert "Line 1" in result["content"]
        assert "Line 2" in result["content"]
        assert "Line 3" in result["content"]
        assert result["metadata"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_full_read_metadata(self, adaptive_reader, small_file):
        """Test full_read metadata."""
        result = await adaptive_reader.smart_read(small_file)

        assert "file_size" in result["metadata"]
        assert "lines_read" in result["metadata"]
        assert result["metadata"]["file_size"] > 0


class TestSmartReadGrep:
    """Tests for smart_read with grep strategy."""

    @pytest.mark.asyncio
    async def test_grep_with_matches(self, adaptive_reader, searchable_file):
        """Test grep strategy finding matches."""
        result = await adaptive_reader.smart_read(
            searchable_file, query="PATTERN_MATCH"
        )

        assert result["strategy"] == "grep"
        assert result["metadata"]["matches_found"] > 0
        assert "PATTERN_MATCH" in result["content"]

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, adaptive_reader, searchable_file):
        """Test grep strategy with no matches."""
        result = await adaptive_reader.smart_read(
            searchable_file, query="NONEXISTENT_PATTERN"
        )

        assert result["strategy"] == "grep"
        assert result["metadata"]["matches_found"] == 0

    @pytest.mark.asyncio
    async def test_grep_metadata(self, adaptive_reader, searchable_file):
        """Test grep metadata."""
        result = await adaptive_reader.smart_read(
            searchable_file, query="PATTERN_MATCH"
        )

        assert "file_size" in result["metadata"]
        assert "matches_found" in result["metadata"]
        assert "query" in result["metadata"]
        assert result["metadata"]["query"] == "PATTERN_MATCH"


class TestSmartReadHeadTail:
    """Tests for smart_read with head_tail strategy."""

    @pytest.mark.asyncio
    async def test_head_tail_large_file(self, adaptive_reader, large_file):
        """Test head_tail strategy on large file."""
        result = await adaptive_reader.smart_read(large_file, max_lines=10)

        assert result["strategy"] == "head_tail"
        # Should have head content
        assert "Line 1:" in result["content"]
        # Should have tail content
        assert "Line 99:" in result["content"]

    @pytest.mark.asyncio
    async def test_head_tail_metadata(self, adaptive_reader, large_file):
        """Test head_tail metadata."""
        result = await adaptive_reader.smart_read(large_file, max_lines=10)

        assert "file_size" in result["metadata"]
        assert "total_lines" in result["metadata"]
        assert "head_lines" in result["metadata"]
        assert "tail_lines" in result["metadata"]
        assert "skipped_lines" in result["metadata"]

    @pytest.mark.asyncio
    async def test_head_tail_shows_skipped(self, adaptive_reader, large_file):
        """Test that head_tail shows skipped lines indicator."""
        result = await adaptive_reader.smart_read(large_file, max_lines=10)

        if result["metadata"]["skipped_lines"] > 0:
            assert "Skipped" in result["content"]


class TestSmartReadErrorHandling:
    """Tests for smart_read error handling."""

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, adaptive_reader, temp_dir):
        """Test handling of nonexistent file."""
        nonexistent = temp_dir / "nonexistent.txt"
        result = await adaptive_reader.smart_read(nonexistent)

        assert result["strategy"] == "error"
        assert "not found" in result["content"].lower()

    @pytest.mark.asyncio
    async def test_relative_path(self, adaptive_reader, sandbox, temp_dir):
        """Test reading with relative path."""
        file_path = temp_dir / "relative_test.txt"
        file_path.write_text("Test content")

        # Use relative path
        result = await adaptive_reader.smart_read(Path("relative_test.txt"))

        assert result["strategy"] == "full_read"
        assert "Test content" in result["content"]


class TestGetFileInfo:
    """Tests for get_file_info method."""

    @pytest.mark.asyncio
    async def test_file_info_exists(self, adaptive_reader, small_file):
        """Test getting info for existing file."""
        info = await adaptive_reader.get_file_info(small_file)

        assert info["exists"] is True
        assert "size_bytes" in info
        assert "size_human" in info
        assert "recommended_strategy" in info
        assert info["recommended_strategy"] == "full_read"

    @pytest.mark.asyncio
    async def test_file_info_not_exists(self, adaptive_reader, temp_dir):
        """Test getting info for nonexistent file."""
        nonexistent = temp_dir / "nonexistent.txt"
        info = await adaptive_reader.get_file_info(nonexistent)

        assert info["exists"] is False
        assert "error" in info

    @pytest.mark.asyncio
    async def test_file_info_thresholds(self, adaptive_reader, small_file):
        """Test that file info includes thresholds."""
        info = await adaptive_reader.get_file_info(small_file)

        assert "thresholds" in info
        assert info["thresholds"]["small"] == 500
        assert info["thresholds"]["medium"] == 2000


class TestFormatSize:
    """Tests for the _format_size utility method."""

    def test_format_bytes(self):
        """Test formatting bytes."""
        assert AdaptiveFileReader._format_size(500) == "500 B"

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        assert AdaptiveFileReader._format_size(1024) == "1.0 KB"
        assert AdaptiveFileReader._format_size(2048) == "2.0 KB"

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        assert AdaptiveFileReader._format_size(1024 * 1024) == "1.0 MB"
        assert AdaptiveFileReader._format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        assert AdaptiveFileReader._format_size(1024 * 1024 * 1024) == "1.0 GB"


class TestGetFileSize:
    """Tests for the _get_file_size method."""

    def test_get_file_size_absolute(self, adaptive_reader, small_file):
        """Test getting file size with absolute path."""
        size = adaptive_reader._get_file_size(small_file)
        assert size > 0

    def test_get_file_size_relative(self, adaptive_reader, sandbox, temp_dir):
        """Test getting file size with relative path."""
        file_path = temp_dir / "size_test.txt"
        file_path.write_text("Test content")

        size = adaptive_reader._get_file_size(Path("size_test.txt"))
        assert size > 0

    def test_get_file_size_not_found(self, adaptive_reader):
        """Test getting file size for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            adaptive_reader._get_file_size(Path("nonexistent.txt"))
