"""
Cache interfaces for the multi-tier caching system.

This module defines interfaces for all cache components:
- ICacheBackend: Low-level cache storage
- IFileStateTracker: File change detection
- IContentCache: File content caching
- ISearchCache: Search result caching
- ICacheManager: Unified cache coordination
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.cache.file_state import FileState


class ICacheBackend(ABC):
    """
    Abstract interface for cache storage backends.

    Implementations provide the low-level storage mechanism for cached data.
    This could be in-memory, disk-based, or distributed cache backends.

    Implementations:
        - PersistentCache: DiskCache-based persistent storage with LRU eviction

    Example:
        ```python
        class InMemoryCache(ICacheBackend):
            def __init__(self):
                self._data = {}

            async def get(self, key: str) -> Optional[Any]:
                return self._data.get(key)

            async def set(self, key: str, value: Any, expire: Optional[float] = None) -> None:
                self._data[key] = value

            async def delete(self, key: str) -> bool:
                return self._data.pop(key, None) is not None

            async def clear(self) -> None:
                self._data.clear()

            def stats(self) -> dict:
                return {"size": len(self._data), "volume": 0, "directory": "memory"}

            def close(self) -> None:
                self._data.clear()
        ```
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Args:
            key: The cache key

        Returns:
            The cached value if found, None otherwise
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, expire: Optional[float] = None) -> None:
        """
        Store a value in the cache.

        Args:
            key: The cache key
            value: The value to cache (must be serializable)
            expire: Optional TTL in seconds (None = no expiry)
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: The cache key

        Returns:
            True if the key was found and deleted, False if not found
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from the cache."""
        pass

    @abstractmethod
    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary containing:
                - size: Number of entries
                - volume: Total size in bytes
                - directory: Cache storage location
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the cache and release resources."""
        pass


class IFileStateTracker(ABC):
    """
    Abstract interface for tracking file states.

    Implementations track file modification times, sizes, and content hashes
    to detect when cached content has become stale.

    Implementations:
        - FileStateTracker: Production implementation using PersistentCache

    Example:
        ```python
        # Check if a file has changed since it was cached
        if await tracker.is_stale(Path("data.txt")):
            # File has changed, reload content
            content = load_file(path)
            await tracker.update_state(path)
        ```
    """

    @abstractmethod
    async def get_state(self, path: Path) -> Optional["FileState"]:
        """
        Get cached file state.

        Args:
            path: Path to the file

        Returns:
            Cached FileState if exists, None otherwise
        """
        pass

    @abstractmethod
    async def update_state(self, path: Path) -> "FileState":
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
        pass

    @abstractmethod
    async def is_stale(self, path: Path) -> bool:
        """
        Check if cached state differs from current file state.

        A file is considered stale if:
        - No cached state exists
        - The file has been deleted
        - The file's mtime, size, or content hash has changed

        Args:
            path: Path to the file

        Returns:
            True if the cached state is stale (file has changed or doesn't exist),
            False if the cached state matches the current state
        """
        pass


class IContentCache(ABC):
    """
    Abstract interface for file content caching.

    Implementations cache file content with automatic staleness detection
    based on file state tracking.

    Implementations:
        - ContentCache: Production implementation with FileStateTracker integration

    Example:
        ```python
        async def load_file(path: Path) -> str:
            return path.read_text()

        # Get content (from cache or fresh if stale)
        content = await cache.get_content(Path("data.txt"), load_file)

        # Invalidate after external modification
        await cache.invalidate(Path("data.txt"))
        ```
    """

    @abstractmethod
    async def get_content(
        self,
        path: Path,
        loader: Callable[[Path], Awaitable[str]],
        ttl: Optional[float] = None,
    ) -> str:
        """
        Get file content, loading if not cached or stale.

        This method implements a cache-aside pattern with automatic staleness
        detection. It always returns the FULL file content.

        Args:
            path: Path to the file
            loader: Async callable to load content on cache miss
            ttl: Optional TTL override in seconds

        Returns:
            The full file content as a string
        """
        pass

    @abstractmethod
    async def invalidate(self, path: Path) -> None:
        """
        Invalidate cache for a specific file.

        Args:
            path: Path to the file to invalidate
        """
        pass

    @abstractmethod
    async def invalidate_directory(self, directory: Path) -> int:
        """
        Invalidate all cached files in a directory.

        Uses proper path-segment boundary matching:
        - /data will match /data/file.txt and /data/subdir/file.txt
        - /data will NOT match /data2 or /data_backup

        Args:
            directory: Path to the directory

        Returns:
            Number of cache entries invalidated
        """
        pass


class ISearchCache(ABC):
    """
    Abstract interface for search result caching.

    Implementations cache search results (grep, find) with scope-aware
    invalidation based on file changes in the search scope.

    Implementations:
        - SearchCache: Production implementation with deterministic key generation

    Example:
        ```python
        # Try to get cached result
        result = await cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=Path("/project"),
            options={"case_sensitive": True}
        )

        if result is None:
            # Cache miss - execute search and cache result
            result = await execute_search(...)
            await cache.set_search_result(
                operation="grep",
                pattern="TODO",
                scope=Path("/project"),
                options={"case_sensitive": True},
                result=result,
                ttl=300
            )
        ```
    """

    @abstractmethod
    async def get_search_result(
        self,
        operation: str,
        pattern: str,
        scope: Path,
        options: dict,
    ) -> Optional[str]:
        """
        Get cached search result if scope hasn't changed.

        Args:
            operation: Search operation type (e.g., "grep", "find")
            pattern: Search pattern
            scope: Directory or file path that was searched
            options: Search options used in the original search

        Returns:
            Cached search result string if valid, None if cache miss or stale
        """
        pass

    @abstractmethod
    async def set_search_result(
        self,
        operation: str,
        pattern: str,
        scope: Path,
        options: dict,
        result: str,
        ttl: Optional[float] = None,
    ) -> None:
        """
        Cache search result with scope state tracking.

        Args:
            operation: Search operation type
            pattern: Search pattern
            scope: Directory or file path
            options: Search options
            result: Search result to cache
            ttl: Optional TTL override in seconds
        """
        pass

    @abstractmethod
    async def invalidate_pattern(
        self,
        operation: str,
        pattern: str,
        scope: Path,
        options: dict,
    ) -> bool:
        """
        Manually invalidate a specific search cache entry.

        Args:
            operation: Search operation type
            pattern: Search pattern
            scope: Directory or file path
            options: Search options

        Returns:
            True if entry was found and deleted, False otherwise
        """
        pass


class ICacheManager(ABC):
    """
    Abstract interface for the unified cache manager.

    Implementations coordinate all cache components (persistent cache,
    file state tracker, content cache, search cache) into a unified interface.

    Implementations:
        - CacheManager: Production implementation coordinating all cache components

    Example:
        ```python
        # Get comprehensive cache statistics
        stats = manager.stats()
        print(f"Total entries: {stats['disk_cache']['size']}")

        # Clear all caches
        await manager.clear_all()

        # Use as context manager
        async with CacheManager.default() as manager:
            # ... use manager ...
        ```
    """

    @property
    @abstractmethod
    def persistent_cache(self) -> ICacheBackend:
        """Get the underlying persistent cache backend."""
        pass

    @property
    @abstractmethod
    def file_state_tracker(self) -> IFileStateTracker:
        """Get the file state tracker."""
        pass

    @property
    @abstractmethod
    def content_cache(self) -> IContentCache:
        """Get the content cache."""
        pass

    @property
    @abstractmethod
    def search_cache(self) -> ISearchCache:
        """Get the search cache."""
        pass

    @abstractmethod
    def stats(self) -> dict:
        """
        Get comprehensive cache statistics.

        Returns:
            Dictionary containing:
                - enabled: Whether the cache is enabled
                - disk_cache: PersistentCache statistics
                - content_ttl: Configured TTL for content cache
                - search_ttl: Configured TTL for search cache
                - configuration: Cache manager configuration settings
        """
        pass

    @abstractmethod
    async def clear_all(self) -> None:
        """Clear all caches and reset all tracking state."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the cache manager and release resources."""
        pass
