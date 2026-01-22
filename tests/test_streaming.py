"""
Tests for the streaming file reader module.
"""

import pytest
from pathlib import Path
import tempfile
import os

from app.agent.tools.streaming import StreamingFileReader


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir).resolve()
        yield test_dir


@pytest.fixture
def small_file(temp_dir):
    """Create a small test file."""
    file_path = temp_dir / "small.txt"
    content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def large_file(temp_dir):
    """Create a larger test file for chunked reading."""
    file_path = temp_dir / "large.txt"
    # Create a file with ~100 lines
    lines = [f"Line {i}: This is some test content for line number {i}\n" for i in range(1, 101)]
    file_path.write_text("".join(lines))
    return file_path


@pytest.fixture
def searchable_file(temp_dir):
    """Create a file with searchable patterns."""
    file_path = temp_dir / "searchable.txt"
    content = """Line 1: Hello World
Line 2: This is a test
Line 3: Hello again
Line 4: Another line
Line 5: Hello there
Line 6: Final line
"""
    file_path.write_text(content)
    return file_path


@pytest.fixture
def streaming_reader():
    """Create a StreamingFileReader instance."""
    return StreamingFileReader(chunk_size=1024)  # 1KB chunks for testing


class TestStreamingFileReaderInit:
    """Tests for StreamingFileReader initialization."""

    def test_default_chunk_size(self):
        """Test default chunk size is 1MB."""
        reader = StreamingFileReader()
        assert reader.chunk_size == 1024 * 1024

    def test_custom_chunk_size(self):
        """Test custom chunk size."""
        reader = StreamingFileReader(chunk_size=4096)
        assert reader.chunk_size == 4096


class TestReadChunks:
    """Tests for the read_chunks method."""

    @pytest.mark.asyncio
    async def test_read_small_file(self, streaming_reader, small_file):
        """Test reading a small file in chunks."""
        chunks = []
        async for chunk in streaming_reader.read_chunks(small_file):
            chunks.append(chunk)

        # Small file should be read in one chunk
        assert len(chunks) >= 1
        content = "".join(chunks)
        assert "Line 1" in content
        assert "Line 5" in content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, streaming_reader, temp_dir):
        """Test reading a file that doesn't exist."""
        nonexistent = temp_dir / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            async for _ in streaming_reader.read_chunks(nonexistent):
                pass

    @pytest.mark.asyncio
    async def test_chunk_concatenation(self, streaming_reader, large_file):
        """Test that chunks concatenate to full content."""
        chunks = []
        async for chunk in streaming_reader.read_chunks(large_file):
            chunks.append(chunk)

        content = "".join(chunks)
        assert "Line 1:" in content
        assert "Line 100:" in content


class TestReadWithCallback:
    """Tests for the read_with_callback method."""

    @pytest.mark.asyncio
    async def test_callback_called(self, streaming_reader, small_file):
        """Test that callback is called for each chunk."""
        chunks_received = []
        bytes_received = []

        def callback(chunk, total_bytes):
            chunks_received.append(chunk)
            bytes_received.append(total_bytes)

        total = await streaming_reader.read_with_callback(small_file, callback)

        assert len(chunks_received) >= 1
        assert total > 0
        assert bytes_received[-1] == total

    @pytest.mark.asyncio
    async def test_callback_bytes_increasing(self, streaming_reader, large_file):
        """Test that bytes count increases with each callback."""
        bytes_received = []

        def callback(chunk, total_bytes):
            bytes_received.append(total_bytes)

        await streaming_reader.read_with_callback(large_file, callback)

        # Bytes should be monotonically increasing
        for i in range(1, len(bytes_received)):
            assert bytes_received[i] >= bytes_received[i - 1]


class TestSearchInLargeFile:
    """Tests for the search_in_large_file method."""

    @pytest.mark.asyncio
    async def test_basic_search(self, streaming_reader, searchable_file):
        """Test basic pattern search."""
        matches = await streaming_reader.search_in_large_file(
            searchable_file, "Hello"
        )

        assert len(matches) == 3
        assert matches[0]["line_number"] == 1
        assert matches[1]["line_number"] == 3
        assert matches[2]["line_number"] == 5

    @pytest.mark.asyncio
    async def test_search_with_regex(self, streaming_reader, searchable_file):
        """Test regex pattern search."""
        matches = await streaming_reader.search_in_large_file(
            searchable_file, r"Line \d:"
        )

        assert len(matches) == 6

    @pytest.mark.asyncio
    async def test_search_max_matches(self, streaming_reader, searchable_file):
        """Test limiting number of matches."""
        matches = await streaming_reader.search_in_large_file(
            searchable_file, "Line", max_matches=2
        )

        assert len(matches) == 2

    @pytest.mark.asyncio
    async def test_search_no_matches(self, streaming_reader, searchable_file):
        """Test search with no matches."""
        matches = await streaming_reader.search_in_large_file(
            searchable_file, "NONEXISTENT_PATTERN"
        )

        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_search_match_positions(self, streaming_reader, searchable_file):
        """Test that match positions are correct."""
        matches = await streaming_reader.search_in_large_file(
            searchable_file, "Hello"
        )

        for match in matches:
            assert "match_start" in match
            assert "match_end" in match
            assert match["match_start"] < match["match_end"]
            # Verify the match is at the correct position in the line
            line = match["line_content"]
            assert line[match["match_start"]:match["match_end"]] == "Hello"

    @pytest.mark.asyncio
    async def test_search_invalid_regex(self, streaming_reader, searchable_file):
        """Test that invalid regex raises error."""
        with pytest.raises(Exception):  # re.error
            await streaming_reader.search_in_large_file(
                searchable_file, "[invalid("
            )


class TestReadLines:
    """Tests for the read_lines method."""

    @pytest.mark.asyncio
    async def test_read_all_lines(self, streaming_reader, small_file):
        """Test reading all lines."""
        lines = []
        async for line_num, content in streaming_reader.read_lines(small_file):
            lines.append((line_num, content))

        assert len(lines) == 5
        assert lines[0] == (1, "Line 1")
        assert lines[4] == (5, "Line 5")

    @pytest.mark.asyncio
    async def test_read_line_range(self, streaming_reader, small_file):
        """Test reading specific line range."""
        lines = []
        async for line_num, content in streaming_reader.read_lines(
            small_file, start_line=2, end_line=4
        ):
            lines.append((line_num, content))

        assert len(lines) == 3
        assert lines[0][0] == 2
        assert lines[2][0] == 4

    @pytest.mark.asyncio
    async def test_read_from_start_line(self, streaming_reader, small_file):
        """Test reading from a specific start line."""
        lines = []
        async for line_num, content in streaming_reader.read_lines(
            small_file, start_line=3
        ):
            lines.append(line_num)

        assert lines == [3, 4, 5]


class TestGetFileStats:
    """Tests for the get_file_stats method."""

    @pytest.mark.asyncio
    async def test_file_stats(self, streaming_reader, small_file):
        """Test getting file statistics."""
        stats = await streaming_reader.get_file_stats(small_file)

        assert "size_bytes" in stats
        assert "line_count" in stats
        assert "is_binary" in stats
        assert stats["size_bytes"] > 0
        assert stats["is_binary"] is False

    @pytest.mark.asyncio
    async def test_binary_detection(self, streaming_reader, temp_dir):
        """Test binary file detection."""
        binary_file = temp_dir / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04")

        stats = await streaming_reader.get_file_stats(binary_file)

        assert stats["is_binary"] is True
