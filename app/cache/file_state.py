"""
File state tracking for cache invalidation.

This module provides functionality to track file states (modification time, size, content hash)
and detect when files have changed, enabling intelligent cache invalidation.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.cache.disk_cache import PersistentCache


@dataclass(frozen=True)
class FileState:
    """
    Immutable file state for change detection.

    Attributes:
        mtime: File modification time (timestamp)
        size: File size in bytes
        content_hash: Optional MD5 hash of file content (computed for files < 1MB)
    """
    mtime: float
    size: int
    content_hash: Optional[str] = None

    @classmethod
    def from_path(cls, path: Path, hash_content: bool = False) -> "FileState":
        """
        Create FileState from a file path.

        Args:
            path: Path to the file
            hash_content: If True, compute content hash for files < 1MB

        Returns:
            FileState object representing the current state of the file

        Raises:
            FileNotFoundError: If the file does not exist
            OSError: If there are permission issues accessing the file
        """
        stat = path.stat()
        content_hash = None

        # Only compute hash for files (not directories) under 1MB
        if hash_content and path.is_file() and stat.st_size < 1_000_000:  # < 1MB
            content_hash = cls._compute_hash(path)

        return cls(
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=content_hash,
        )

    @staticmethod
    def _compute_hash(path: Path) -> str:
        """
        Compute MD5 hash of file content.

        Args:
            path: Path to the file

        Returns:
            Hexadecimal MD5 hash string

        Raises:
            OSError: If the file cannot be read
        """
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()


class FileStateTracker:
    """
    Track and compare file states for cache invalidation.

    This class maintains a cache of file states and provides methods to detect
    when files have been modified by comparing cached state with current state.
    """

    def __init__(self, cache: "PersistentCache"):
        """
        Initialize the file state tracker.

        Args:
            cache: PersistentCache instance for storing file states
        """
        self._cache = cache
        self._state_prefix = "_filestate:"

    async def get_state(self, path: Path) -> Optional[FileState]:
        """
        Get cached file state.

        Args:
            path: Path to the file

        Returns:
            Cached FileState if exists, None otherwise
        """
        key = f"{self._state_prefix}{path.resolve()}"
        return await self._cache.get(key)

    async def update_state(self, path: Path) -> FileState:
        """
        Update cached file state with current state.

        Computes current file state (including content hash for files < 1MB)
        and stores it in the cache.

        Args:
            path: Path to the file

        Returns:
            The computed FileState

        Raises:
            FileNotFoundError: If the file does not exist
            OSError: If there are permission issues accessing the file
        """
        state = FileState.from_path(path, hash_content=True)
        key = f"{self._state_prefix}{path.resolve()}"
        await self._cache.set(key, state)
        return state

    async def is_stale(self, path: Path) -> bool:
        """
        Check if cached state differs from current file state.

        This method compares the cached file state with the current state
        to determine if the file has been modified. A file is considered
        stale if:
        - No cached state exists
        - The file has been deleted
        - The file's mtime, size, or content hash has changed

        Args:
            path: Path to the file

        Returns:
            True if the cached state is stale (file has changed or doesn't exist),
            False if the cached state matches the current state
        """
        cached = await self.get_state(path)
        if cached is None:
            return True

        try:
            current = FileState.from_path(path, hash_content=cached.content_hash is not None)
            return current != cached
        except FileNotFoundError:
            return True  # File deleted = stale
