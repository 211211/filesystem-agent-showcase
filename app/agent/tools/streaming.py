"""
Streaming file reader for handling large files efficiently.
Provides async generators for chunked reading and pattern searching.
"""

import re
from pathlib import Path
from typing import AsyncGenerator, Callable, List, Optional

import aiofiles


class StreamingFileReader:
    """
    Reads files in chunks asynchronously to handle large files efficiently.

    This class provides methods for:
    - Streaming file content in configurable chunks
    - Reading with callbacks for progress tracking
    - Searching patterns in large files without loading entire content
    """

    def __init__(self, chunk_size: int = 1024 * 1024):  # 1MB default
        """
        Initialize the streaming file reader.

        Args:
            chunk_size: Size of each chunk in bytes (default: 1MB)
        """
        self.chunk_size = chunk_size

    async def read_chunks(self, file_path: Path) -> AsyncGenerator[str, None]:
        """
        Async generator to stream file content in chunks.

        Args:
            file_path: Path to the file to read

        Yields:
            String chunks of the file content

        Raises:
            FileNotFoundError: If the file does not exist
            PermissionError: If the file cannot be read
        """
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8', errors='replace') as f:
                while True:
                    chunk = await f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except UnicodeDecodeError:
            # Fallback to binary reading with explicit decode
            async with aiofiles.open(file_path, mode='rb') as f:
                while True:
                    chunk = await f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk.decode('utf-8', errors='replace')

    async def read_with_callback(
        self,
        file_path: Path,
        on_chunk: Callable[[str, int], None]
    ) -> int:
        """
        Read file and call callback for each chunk.

        Args:
            file_path: Path to the file to read
            on_chunk: Callback function receiving (chunk_content, bytes_read_so_far)

        Returns:
            Total bytes read

        Raises:
            FileNotFoundError: If the file does not exist
            PermissionError: If the file cannot be read
        """
        total_bytes = 0

        async for chunk in self.read_chunks(file_path):
            chunk_bytes = len(chunk.encode('utf-8'))
            total_bytes += chunk_bytes
            on_chunk(chunk, total_bytes)

        return total_bytes

    async def search_in_large_file(
        self,
        file_path: Path,
        pattern: str,
        max_matches: int = 100,
        context_lines: int = 0
    ) -> List[dict]:
        """
        Search pattern in large file without loading entire file.

        Args:
            file_path: Path to the file to search
            pattern: Regex pattern to search for
            max_matches: Maximum number of matches to return (default: 100)
            context_lines: Number of context lines before/after match (default: 0)

        Returns:
            List of match dictionaries with keys:
            - line_number: int
            - line_content: str
            - match_start: int (position in line)
            - match_end: int (position in line)
            - context_before: List[str] (if context_lines > 0)
            - context_after: List[str] (if context_lines > 0)

        Raises:
            FileNotFoundError: If the file does not exist
            re.error: If the pattern is invalid
        """
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{pattern}': {e}")

        matches: List[dict] = []
        line_number = 0
        context_buffer: List[str] = []
        pending_matches: List[dict] = []  # Matches waiting for context_after

        async with aiofiles.open(
            file_path, mode='r', encoding='utf-8', errors='replace'
        ) as f:
            async for line in f:
                line_number += 1
                line = line.rstrip('\n\r')

                # Update context buffer for context_before
                if context_lines > 0:
                    context_buffer.append(line)
                    if len(context_buffer) > context_lines + 1:
                        context_buffer.pop(0)

                # Add context_after to pending matches
                for pending in pending_matches[:]:
                    if len(pending.get('context_after', [])) < context_lines:
                        pending['context_after'].append(line)
                    if len(pending.get('context_after', [])) >= context_lines:
                        matches.append(pending)
                        pending_matches.remove(pending)
                        if len(matches) >= max_matches:
                            break

                if len(matches) >= max_matches:
                    break

                # Search for pattern in current line
                match = regex.search(line)
                if match:
                    match_info = {
                        'line_number': line_number,
                        'line_content': line,
                        'match_start': match.start(),
                        'match_end': match.end(),
                    }

                    if context_lines > 0:
                        # Add context_before (excluding current line)
                        match_info['context_before'] = context_buffer[:-1].copy()
                        match_info['context_after'] = []
                        pending_matches.append(match_info)
                    else:
                        if len(matches) < max_matches:
                            matches.append(match_info)

        # Add any remaining pending matches (at end of file)
        for pending in pending_matches:
            if len(matches) < max_matches:
                matches.append(pending)

        return matches

    async def read_lines(
        self,
        file_path: Path,
        start_line: int = 1,
        end_line: Optional[int] = None
    ) -> AsyncGenerator[tuple[int, str], None]:
        """
        Read specific line range from a file.

        Args:
            file_path: Path to the file to read
            start_line: First line to read (1-indexed, default: 1)
            end_line: Last line to read (inclusive, None for all remaining)

        Yields:
            Tuples of (line_number, line_content)
        """
        line_number = 0

        async with aiofiles.open(
            file_path, mode='r', encoding='utf-8', errors='replace'
        ) as f:
            async for line in f:
                line_number += 1

                if line_number < start_line:
                    continue

                if end_line is not None and line_number > end_line:
                    break

                yield (line_number, line.rstrip('\n\r'))

    async def get_file_stats(self, file_path: Path) -> dict:
        """
        Get statistics about a file without reading entire content.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file statistics:
            - size_bytes: int
            - line_count: int (estimated for very large files)
            - is_binary: bool
        """
        stat = file_path.stat()
        size_bytes = stat.st_size

        # Sample the file to determine if binary and estimate line count
        sample_size = min(size_bytes, 8192)  # Read up to 8KB sample
        line_count = 0
        is_binary = False

        try:
            async with aiofiles.open(file_path, mode='rb') as f:
                sample = await f.read(sample_size)

                # Check for binary content (null bytes)
                if b'\x00' in sample:
                    is_binary = True
                else:
                    # Count newlines in sample
                    newlines_in_sample = sample.count(b'\n')
                    if sample_size < size_bytes:
                        # Estimate total lines based on sample
                        line_count = int((newlines_in_sample / sample_size) * size_bytes)
                    else:
                        line_count = newlines_in_sample
        except Exception:
            pass

        return {
            'size_bytes': size_bytes,
            'line_count': line_count,
            'is_binary': is_binary,
        }
