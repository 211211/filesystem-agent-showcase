"""
Content cache with automatic staleness detection.

This module provides the ContentCache class that caches file content with
intelligent invalidation based on file state tracking. It automatically
detects when cached content is stale by comparing file modification times,
sizes, and content hashes.
"""

from pathlib import Path
from typing import Callable, Awaitable
import logging

from app.cache.disk_cache import PersistentCache
from app.cache.file_state import FileStateTracker

logger = logging.getLogger(__name__)


class ContentCache:
    """
    Cache file content with automatic staleness detection.

    This class provides a high-level interface for caching file content
    while automatically detecting when files have changed. It integrates
    with PersistentCache for storage and FileStateTracker for change
    detection.

    Attributes:
        _cache: The underlying PersistentCache instance
        _tracker: FileStateTracker for detecting file changes
        _content_prefix: Prefix for all content cache keys

    Example:
        >>> cache = PersistentCache()
        >>> tracker = FileStateTracker(cache)
        >>> content_cache = ContentCache(cache, tracker)
        >>>
        >>> async def load_file(path: Path) -> str:
        ...     return path.read_text()
        >>>
        >>> # Get content (from cache or load fresh if stale)
        >>> content = await content_cache.get_content(
        ...     Path("example.txt"),
        ...     load_file
        ... )
        >>>
        >>> # Invalidate specific file
        >>> await content_cache.invalidate(Path("example.txt"))
        >>>
        >>> # Invalidate entire directory
        >>> count = await content_cache.invalidate_directory(Path("docs/"))
        >>> print(f"Invalidated {count} files")
    """

    def __init__(
        self,
        disk_cache: PersistentCache,
        state_tracker: FileStateTracker,
    ):
        """
        Initialize the content cache.

        Args:
            disk_cache: PersistentCache instance for storing content
            state_tracker: FileStateTracker instance for staleness detection
        """
        self._cache = disk_cache
        self._tracker = state_tracker
        self._content_prefix = "_content:"

    async def get_content(
        self,
        path: Path,
        loader: Callable[[Path], Awaitable[str]],
    ) -> str:
        """
        Get file content, loading if not cached or stale.

        This method implements a cache-aside pattern with automatic staleness
        detection. It will:
        1. Check if the file state is stale using FileStateTracker
        2. If not stale and cached, return cached content (cache hit)
        3. If stale or not cached, call the loader to get fresh content
        4. Store the fresh content in cache and update file state
        5. Return the content

        Args:
            path: Path to the file to retrieve content for
            loader: Async callable that loads content from the file.
                   Should accept a Path and return the file content as string.
                   This is only called on cache miss or stale cache.

        Returns:
            The file content as a string (from cache or freshly loaded)

        Raises:
            Any exceptions raised by the loader function will propagate up

        Example:
            >>> async def read_text(p: Path) -> str:
            ...     return p.read_text(encoding='utf-8')
            >>>
            >>> content = await cache.get_content(
            ...     Path("data/document.txt"),
            ...     read_text
            ... )
            >>> print(f"Content length: {len(content)}")

        Note:
            The path is resolved to an absolute path before caching to ensure
            consistency regardless of the current working directory.
        """
        resolved = path.resolve()
        key = f"{self._content_prefix}{resolved}"

        # Check if cached and not stale
        if not await self._tracker.is_stale(resolved):
            cached = await self._cache.get(key)
            if cached is not None:
                logger.debug(f"Cache HIT: {path}")
                return cached

        # Cache miss or stale - load fresh
        logger.debug(f"Cache MISS/STALE: {path}")
        content = await loader(path)

        # Update cache and state
        await self._cache.set(key, content)
        await self._tracker.update_state(resolved)

        return content

    async def invalidate(self, path: Path) -> None:
        """
        Invalidate cache for a specific file.

        This removes the cached content for the specified file. The next
        call to get_content() for this file will trigger a fresh load.

        Args:
            path: Path to the file to invalidate

        Example:
            >>> # Update a file
            >>> Path("data.txt").write_text("new content")
            >>>
            >>> # Invalidate its cache
            >>> await cache.invalidate(Path("data.txt"))
            >>>
            >>> # Next access will reload from disk
            >>> content = await cache.get_content(Path("data.txt"), loader)

        Note:
            This only removes the cached content, not the file state.
            The file state will be updated on the next get_content() call.
        """
        resolved = path.resolve()
        key = f"{self._content_prefix}{resolved}"
        await self._cache.delete(key)
        logger.debug(f"Cache INVALIDATED: {path}")

    async def invalidate_directory(self, directory: Path) -> int:
        """
        Invalidate all cached files in a directory.

        This method iterates through all cache keys and removes entries
        for files that are within the specified directory (including
        subdirectories).

        Args:
            directory: Path to the directory to invalidate

        Returns:
            The number of cache entries that were invalidated

        Example:
            >>> # Invalidate all cached files in docs/ directory
            >>> count = await cache.invalidate_directory(Path("docs"))
            >>> print(f"Invalidated {count} cached files")

        Warning:
            This operation can be expensive for large caches as it requires
            iterating through all cache keys. Use sparingly and consider
            invalidating specific files when possible.

        Note:
            This uses DiskCache's iterkeys() method which is safe for
            concurrent access. The iteration is performed synchronously
            but each delete operation is async.
        """
        # This requires iterating cache keys - expensive but necessary
        # DiskCache supports this via iterkeys()
        count = 0
        prefix = f"{self._content_prefix}{directory.resolve()}"

        # Note: DiskCache iteration is safe
        for key in self._cache._cache.iterkeys():
            if key.startswith(prefix):
                await self._cache.delete(key)
                count += 1

        logger.debug(f"Cache INVALIDATED directory: {directory} ({count} entries)")
        return count
