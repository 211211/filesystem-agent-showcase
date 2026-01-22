"""
Adaptive file reader that selects the best reading strategy based on file size.
Handles small, medium, and large files with different approaches.
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .streaming import StreamingFileReader

if TYPE_CHECKING:
    from app.sandbox.executor import SandboxExecutor


class AdaptiveFileReader:
    """
    Intelligently reads files based on their size using different strategies:

    - Small files (< 1MB): Read entire file content
    - Medium files (1-100MB) with query: Use grep to search
    - Large files (> 100MB): Read head + tail portions
    """

    # Default size thresholds
    SMALL_FILE = 1_000_000       # 1MB
    MEDIUM_FILE = 100_000_000    # 100MB

    def __init__(
        self,
        sandbox: "SandboxExecutor",
        small_threshold: Optional[int] = None,
        medium_threshold: Optional[int] = None
    ):
        """
        Initialize the adaptive file reader.

        Args:
            sandbox: SandboxExecutor for executing shell commands
            small_threshold: Size threshold for small files (default: 1MB)
            medium_threshold: Size threshold for medium files (default: 100MB)
        """
        self.sandbox = sandbox
        self.streaming_reader = StreamingFileReader()
        self.small_threshold = small_threshold or self.SMALL_FILE
        self.medium_threshold = medium_threshold or self.MEDIUM_FILE

    def _get_file_size(self, file_path: Path) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to the file

        Returns:
            File size in bytes

        Raises:
            FileNotFoundError: If the file does not exist
        """
        resolved_path = file_path
        if not file_path.is_absolute():
            resolved_path = self.sandbox.root_path / file_path

        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        return resolved_path.stat().st_size

    def _select_strategy(self, file_size: int, query: Optional[str] = None) -> str:
        """
        Select the reading strategy based on file size and query.

        Args:
            file_size: Size of the file in bytes
            query: Optional search query

        Returns:
            Strategy name: "full_read", "grep", or "head_tail"
        """
        if file_size <= self.small_threshold:
            return "full_read"
        elif file_size <= self.medium_threshold and query:
            return "grep"
        else:
            return "head_tail"

    async def smart_read(
        self,
        file_path: Path,
        query: Optional[str] = None,
        max_lines: int = 100
    ) -> dict:
        """
        Intelligently read file based on size.

        Args:
            file_path: Path to the file (relative to sandbox root or absolute)
            query: Optional search query for grep strategy
            max_lines: Maximum lines for head/tail (default: 100 each)

        Returns:
            Dictionary with keys:
            - strategy: str ("full_read", "grep", or "head_tail")
            - content: str (file content or search results)
            - metadata: dict with additional info
                - file_size: int
                - lines_read: int (if applicable)
                - matches_found: int (for grep strategy)
                - truncated: bool
        """
        # Resolve path relative to sandbox
        resolved_path = file_path
        if not file_path.is_absolute():
            resolved_path = self.sandbox.root_path / file_path

        if not resolved_path.exists():
            return {
                "strategy": "error",
                "content": f"File not found: {file_path}",
                "metadata": {"error": "FileNotFoundError"}
            }

        try:
            file_size = self._get_file_size(resolved_path)
        except Exception as e:
            return {
                "strategy": "error",
                "content": str(e),
                "metadata": {"error": type(e).__name__}
            }

        strategy = self._select_strategy(file_size, query)

        if strategy == "full_read":
            return await self._full_read(resolved_path, file_size)
        elif strategy == "grep":
            return await self._grep_read(resolved_path, query, file_size)
        else:
            return await self._head_tail_read(resolved_path, max_lines, file_size)

    async def _full_read(self, file_path: Path, file_size: int) -> dict:
        """
        Read entire file content.

        Args:
            file_path: Absolute path to the file
            file_size: Size of the file in bytes

        Returns:
            Result dictionary with full file content
        """
        result = await self.sandbox.execute(["cat", str(file_path)])

        if result.success:
            lines = result.stdout.count('\n') + (1 if result.stdout else 0)
            return {
                "strategy": "full_read",
                "content": result.stdout,
                "metadata": {
                    "file_size": file_size,
                    "lines_read": lines,
                    "truncated": False
                }
            }
        else:
            return {
                "strategy": "full_read",
                "content": result.stderr or "Failed to read file",
                "metadata": {
                    "file_size": file_size,
                    "error": result.error or "UnknownError"
                }
            }

    async def _grep_read(
        self,
        file_path: Path,
        query: str,
        file_size: int
    ) -> dict:
        """
        Search file content using grep.

        Args:
            file_path: Absolute path to the file
            query: Search pattern
            file_size: Size of the file in bytes

        Returns:
            Result dictionary with grep output
        """
        # Use grep with line numbers and limit output
        result = await self.sandbox.execute([
            "grep", "-n", "-m", "100", query, str(file_path)
        ])

        matches_found = 0
        if result.success and result.stdout:
            matches_found = result.stdout.count('\n') + 1

        # Format output with context
        content = result.stdout if result.success else ""
        if not content and result.return_code == 1:
            # grep returns 1 when no matches found (not an error)
            content = f"No matches found for pattern: {query}"

        return {
            "strategy": "grep",
            "content": content,
            "metadata": {
                "file_size": file_size,
                "matches_found": matches_found,
                "query": query,
                "truncated": matches_found >= 100
            }
        }

    async def _head_tail_read(
        self,
        file_path: Path,
        max_lines: int,
        file_size: int
    ) -> dict:
        """
        Read head and tail portions of a large file.

        Args:
            file_path: Absolute path to the file
            max_lines: Number of lines to read from head and tail
            file_size: Size of the file in bytes

        Returns:
            Result dictionary with head + tail content
        """
        # Read head
        head_result = await self.sandbox.execute([
            "head", "-n", str(max_lines), str(file_path)
        ])

        # Read tail
        tail_result = await self.sandbox.execute([
            "tail", "-n", str(max_lines), str(file_path)
        ])

        # Get total line count
        wc_result = await self.sandbox.execute([
            "wc", "-l", str(file_path)
        ])

        total_lines = 0
        if wc_result.success:
            try:
                total_lines = int(wc_result.stdout.strip().split()[0])
            except (ValueError, IndexError):
                pass

        head_content = head_result.stdout if head_result.success else ""
        tail_content = tail_result.stdout if tail_result.success else ""

        # Calculate if there's a gap between head and tail
        head_lines = head_content.count('\n')
        tail_lines = tail_content.count('\n')
        skipped_lines = max(0, total_lines - head_lines - tail_lines)

        # Combine content with separator
        if skipped_lines > 0:
            separator = f"\n\n--- Skipped {skipped_lines} lines ---\n\n"
            content = head_content + separator + tail_content
        else:
            content = head_content

        return {
            "strategy": "head_tail",
            "content": content,
            "metadata": {
                "file_size": file_size,
                "total_lines": total_lines,
                "head_lines": head_lines,
                "tail_lines": tail_lines,
                "skipped_lines": skipped_lines,
                "truncated": skipped_lines > 0
            }
        }

    async def get_file_info(self, file_path: Path) -> dict:
        """
        Get information about a file and recommended reading strategy.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file info and recommended strategy
        """
        resolved_path = file_path
        if not file_path.is_absolute():
            resolved_path = self.sandbox.root_path / file_path

        if not resolved_path.exists():
            return {
                "exists": False,
                "path": str(file_path),
                "error": "File not found"
            }

        try:
            file_size = self._get_file_size(resolved_path)
            stats = await self.streaming_reader.get_file_stats(resolved_path)

            strategy_no_query = self._select_strategy(file_size, query=None)
            strategy_with_query = self._select_strategy(file_size, query="sample")

            return {
                "exists": True,
                "path": str(resolved_path),
                "size_bytes": file_size,
                "size_human": self._format_size(file_size),
                "estimated_lines": stats.get('line_count', 0),
                "is_binary": stats.get('is_binary', False),
                "recommended_strategy": strategy_no_query,
                "strategy_with_query": strategy_with_query,
                "thresholds": {
                    "small": self.small_threshold,
                    "medium": self.medium_threshold
                }
            }
        except Exception as e:
            return {
                "exists": True,
                "path": str(file_path),
                "error": str(e)
            }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
        else:
            return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"
