"""Persistent cache using DiskCache with async support.

This module provides a thread-safe, async-compatible wrapper around the
DiskCache library for persistent caching with automatic LRU eviction.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

from diskcache import Cache


class PersistentCache:
    """Persistent cache using DiskCache with async support.

    This class provides an async-safe interface to DiskCache, using asyncio.Lock
    for thread-safe operations. It supports automatic LRU eviction when the cache
    size exceeds the configured limit.

    Attributes:
        _cache: The underlying DiskCache instance
        _lock: Asyncio lock for thread-safe async operations

    Example:
        >>> cache = PersistentCache()
        >>> await cache.set("key", "value")
        >>> value = await cache.get("key")
        >>> print(value)
        'value'
        >>> stats = cache.stats()
        >>> print(f"Cache size: {stats['size']} items")
    """

    def __init__(
        self,
        cache_dir: str = "tmp/cache",
        size_limit: int = 500 * 1024 * 1024,  # 500MB default
    ):
        """Initialize the persistent cache.

        Args:
            cache_dir: Directory path for storing cache data. Defaults to "tmp/cache".
                      The directory will be created if it doesn't exist.
            size_limit: Maximum cache size in bytes. Defaults to 500MB (524,288,000 bytes).
                       When this limit is exceeded, least-recently-used entries are evicted.

        Note:
            The cache uses the 'least-recently-used' eviction policy, which removes
            the least recently accessed items when the size limit is reached.
        """
        # Create cache directory if it doesn't exist
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        self._cache = Cache(
            directory=cache_dir,
            size_limit=size_limit,
            eviction_policy="least-recently-used",
        )
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache.

        This operation is async-safe and thread-safe through the use of asyncio.Lock.
        Accessing a key updates its access time for LRU tracking.

        Args:
            key: The cache key to retrieve

        Returns:
            The cached value if found, None otherwise

        Example:
            >>> value = await cache.get("my_key")
            >>> if value is None:
            ...     print("Cache miss")
            ... else:
            ...     print(f"Cache hit: {value}")
        """
        async with self._lock:
            return self._cache.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[float] = None
    ) -> None:
        """Store a value in the cache.

        This operation is async-safe and thread-safe. If the cache size exceeds
        the limit after insertion, LRU entries will be automatically evicted.

        Args:
            key: The cache key to store the value under
            value: The value to cache (must be pickle-able)
            expire: Optional expiration time in seconds. If None, the entry
                   never expires (default). Use 0 for immediate expiration.

        Example:
            >>> # Store without expiration
            >>> await cache.set("key1", "permanent_value")
            >>>
            >>> # Store with 5-minute TTL
            >>> await cache.set("key2", "temporary_value", expire=300)

        Note:
            Values must be serializable by pickle. Complex objects like open
            file handles or network connections cannot be cached.
        """
        async with self._lock:
            self._cache.set(key, value, expire=expire)

    async def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        This operation is async-safe and thread-safe.

        Args:
            key: The cache key to delete

        Returns:
            True if the key was found and deleted, False if the key didn't exist

        Example:
            >>> deleted = await cache.delete("my_key")
            >>> if deleted:
            ...     print("Key was deleted")
            ... else:
            ...     print("Key not found")
        """
        async with self._lock:
            return self._cache.delete(key)

    async def clear(self) -> None:
        """Clear all entries from the cache.

        This operation is async-safe and thread-safe. It removes all cached
        entries and resets the cache statistics.

        Warning:
            This operation is irreversible and will permanently remove all
            cached data.

        Example:
            >>> await cache.clear()
            >>> stats = cache.stats()
            >>> assert stats['size'] == 0
        """
        async with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """Get cache statistics.

        This is a synchronous operation that returns current cache metrics.
        It does not require locking as it only reads metadata.

        Returns:
            A dictionary containing:
                - size: Number of entries in the cache
                - volume: Total size of cached data in bytes
                - directory: Path to the cache directory

        Example:
            >>> stats = cache.stats()
            >>> print(f"Entries: {stats['size']}")
            >>> print(f"Size: {stats['volume'] / 1024 / 1024:.2f} MB")
            >>> print(f"Location: {stats['directory']}")

        Note:
            The volume metric represents the actual disk space used,
            which may be larger than the sum of cached values due to
            internal DiskCache overhead.
        """
        return {
            "size": len(self._cache),
            "volume": self._cache.volume(),
            "directory": self._cache.directory,
        }

    async def __aenter__(self):
        """Async context manager entry.

        Example:
            >>> async with PersistentCache() as cache:
            ...     await cache.set("key", "value")
            ...     value = await cache.get("key")
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit.

        Ensures proper cleanup when using the cache as a context manager.
        """
        # DiskCache handles its own cleanup
        pass

    def close(self) -> None:
        """Close the cache and release resources.

        This should be called when the cache is no longer needed to ensure
        proper cleanup of file handles and locks.

        Example:
            >>> cache = PersistentCache()
            >>> # ... use cache ...
            >>> cache.close()

        Note:
            After calling close(), the cache instance should not be used.
        """
        self._cache.close()

    def __del__(self):
        """Destructor to ensure cache is closed on garbage collection."""
        try:
            self._cache.close()
        except Exception:
            # Silently ignore errors during cleanup
            pass
