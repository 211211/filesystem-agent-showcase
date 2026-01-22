"""
File tools for direct file operations.
Provides read, write, and list operations without shell commands.
"""

from pathlib import Path
from typing import Optional
import aiofiles
import aiofiles.os


class FileSizeExceededError(Exception):
    """Raised when a file exceeds the maximum allowed size."""

    def __init__(self, file_path: Path, file_size: int, max_size: int):
        self.file_path = file_path
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(
            f"File '{file_path.name}' ({file_size / 1024 / 1024:.2f} MB) "
            f"exceeds maximum allowed size ({max_size / 1024 / 1024:.2f} MB)"
        )


def check_file_size(file_path: Path, max_size: int) -> int:
    """
    Check if a file is within the allowed size limit.

    Args:
        file_path: Path to the file
        max_size: Maximum allowed size in bytes

    Returns:
        The file size in bytes

    Raises:
        FileSizeExceededError: If the file exceeds the maximum size
        FileNotFoundError: If the file doesn't exist
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size

    if file_size > max_size:
        raise FileSizeExceededError(file_path, file_size, max_size)

    return file_size


async def read_file(file_path: Path, max_size: Optional[int] = None) -> str:
    """
    Read the contents of a file asynchronously.

    Args:
        file_path: Path to the file to read
        max_size: Maximum file size in bytes (None for no limit)

    Returns:
        The file contents as a string

    Raises:
        FileSizeExceededError: If the file exceeds max_size
    """
    if max_size is not None:
        check_file_size(file_path, max_size)

    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
        return await f.read()


async def write_file(file_path: Path, content: str, max_size: Optional[int] = None) -> None:
    """
    Write content to a file asynchronously.

    Args:
        file_path: Path to the file to write
        content: Content to write
        max_size: Maximum content size in bytes (None for no limit)

    Raises:
        FileSizeExceededError: If the content exceeds max_size
    """
    content_size = len(content.encode('utf-8'))

    if max_size is not None and content_size > max_size:
        raise FileSizeExceededError(file_path, content_size, max_size)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
        await f.write(content)


async def list_directory(dir_path: Path, recursive: bool = False) -> list[dict]:
    """List contents of a directory."""
    items = []

    if recursive:
        for item in dir_path.rglob('*'):
            items.append(_path_to_dict(item, dir_path))
    else:
        for item in dir_path.iterdir():
            items.append(_path_to_dict(item, dir_path))

    return sorted(items, key=lambda x: (not x['is_directory'], x['name']))


def _path_to_dict(path: Path, base_path: Path) -> dict:
    """Convert a Path to a dictionary representation."""
    stat = path.stat()
    return {
        'name': path.name,
        'path': str(path.relative_to(base_path)),
        'is_directory': path.is_dir(),
        'size': stat.st_size if path.is_file() else None,
        'modified': stat.st_mtime,
    }


async def file_exists(file_path: Path) -> bool:
    """Check if a file exists asynchronously."""
    return await aiofiles.os.path.exists(file_path)


async def get_file_info(file_path: Path) -> Optional[dict]:
    """Get information about a file."""
    if not file_path.exists():
        return None

    stat = file_path.stat()
    return {
        'name': file_path.name,
        'path': str(file_path),
        'is_directory': file_path.is_dir(),
        'size': stat.st_size if file_path.is_file() else None,
        'modified': stat.st_mtime,
        'extension': file_path.suffix if file_path.is_file() else None,
    }


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{size_bytes / 1024 / 1024 / 1024:.1f} GB"
