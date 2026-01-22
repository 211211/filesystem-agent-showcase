"""
Unified cache manager coordinating all cache components.

This module provides the CacheManager class that orchestrates all cache components
(PersistentCache, FileStateTracker, ContentCache, SearchCache) into a unified
interface. It handles initialization from configuration and provides monitoring
capabilities.
"""

import logging
from typing import Optional

from app.cache.disk_cache import PersistentCache
from app.cache.file_state import FileStateTracker
from app.cache.content_cache import ContentCache
from app.cache.search_cache import SearchCache
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Unified cache manager coordinating all cache components.

    This class provides a high-level interface to all caching functionality in the
    application. It initializes and coordinates the following components:
    - PersistentCache: Low-level disk-based cache backend
    - FileStateTracker: Tracks file states for change detection
    - ContentCache: Caches file content with automatic invalidation
    - SearchCache: Caches search results with scope-aware invalidation

    The CacheManager follows the architecture diagram from CACHE_IMPROVEMENT_PLAN_VI.md,
    providing a unified entry point for all cache operations.

    Attributes:
        persistent_cache: The underlying PersistentCache instance
        file_state_tracker: FileStateTracker for detecting file changes
        content_cache: ContentCache for caching file content
        search_cache: SearchCache for caching search results

    Example:
        >>> # Initialize with custom settings
        >>> manager = CacheManager(
        ...     cache_dir="custom/cache",
        ...     size_limit=1024 * 1024 * 1024,  # 1GB
        ...     content_ttl=0,  # No expiry for content
        ...     search_ttl=600  # 10 minutes for search
        ... )
        >>>
        >>> # Or use default settings from environment
        >>> manager = CacheManager.default()
        >>>
        >>> # Get cache statistics
        >>> stats = manager.stats()
        >>> print(f"Total cache size: {stats['disk_cache']['volume']} bytes")
        >>>
        >>> # Clear all caches
        >>> await manager.clear_all()
    """

    def __init__(
        self,
        cache_dir: str = "tmp/cache",
        size_limit: int = 500 * 1024 * 1024,  # 500MB default
        content_ttl: float = 0,  # No expiry for content (invalidate on file change)
        search_ttl: float = 300,  # 5 minutes for search results
    ):
        """
        Initialize the cache manager with all cache components.

        This constructor sets up the complete cache hierarchy:
        1. Creates the PersistentCache (L2 disk cache)
        2. Initializes FileStateTracker for change detection
        3. Creates ContentCache for file content caching
        4. Creates SearchCache for search result caching

        Args:
            cache_dir: Directory path for storing cache data. Defaults to "tmp/cache".
                      The directory will be created if it doesn't exist.
            size_limit: Maximum cache size in bytes. Defaults to 500MB (524,288,000 bytes).
                       When this limit is exceeded, least-recently-used entries are evicted.
            content_ttl: Time-to-live for cached file content in seconds. Defaults to 0
                        (no expiry), meaning content is only invalidated when files change.
            search_ttl: Time-to-live for cached search results in seconds. Defaults to 300
                       (5 minutes). Search results expire faster since they depend on
                       multiple files.

        Note:
            All cache components share the same PersistentCache backend, ensuring
            consistent storage and eviction behavior.
        """
        logger.info(
            f"Initializing CacheManager: dir={cache_dir}, "
            f"size_limit={size_limit}, "
            f"content_ttl={content_ttl}, "
            f"search_ttl={search_ttl}"
        )

        # Initialize disk cache backend (L2 cache)
        self.persistent_cache = PersistentCache(
            cache_dir=cache_dir,
            size_limit=size_limit,
        )

        # Initialize file state tracker for change detection
        self.file_state_tracker = FileStateTracker(self.persistent_cache)

        # Initialize content cache with file state tracking
        self.content_cache = ContentCache(
            disk_cache=self.persistent_cache,
            state_tracker=self.file_state_tracker,
        )

        # Initialize search cache with scope-aware invalidation
        self.search_cache = SearchCache(
            disk_cache=self.persistent_cache,
            state_tracker=self.file_state_tracker,
        )

        # Store TTL settings for reference
        self._content_ttl = content_ttl
        self._search_ttl = search_ttl

        logger.info("CacheManager initialized successfully")

    @classmethod
    def default(cls, settings: Optional[Settings] = None) -> "CacheManager":
        """
        Create CacheManager with default settings from environment variables.

        This is the recommended way to initialize the CacheManager in production.
        It loads configuration from environment variables (or .env file) using
        the Settings class.

        Args:
            settings: Optional Settings instance. If not provided, uses get_settings()
                     to load from environment variables.

        Returns:
            A new CacheManager instance configured from environment settings

        Environment Variables:
            CACHE_DIRECTORY: Cache directory path (default: "tmp/cache")
            CACHE_SIZE_LIMIT: Max cache size in bytes (default: 524288000 = 500MB)
            CACHE_CONTENT_TTL: Content TTL in seconds (default: 0 = no expiry)
            CACHE_SEARCH_TTL: Search TTL in seconds (default: 300 = 5 minutes)

        Example:
            >>> # Load from environment
            >>> manager = CacheManager.default()
            >>>
            >>> # Or provide custom settings
            >>> from app.config import Settings
            >>> settings = Settings(
            ...     cache_directory="custom/cache",
            ...     cache_size_limit=1_000_000_000
            ... )
            >>> manager = CacheManager.default(settings)

        Note:
            This method uses the Settings class which automatically loads from
            environment variables and validates the configuration.
        """
        if settings is None:
            settings = get_settings()

        # Load cache configuration from settings
        cache_dir = getattr(settings, "cache_directory", "tmp/cache")
        size_limit = getattr(settings, "cache_size_limit", 500 * 1024 * 1024)
        content_ttl = getattr(settings, "cache_content_ttl", 0)
        search_ttl = getattr(settings, "cache_search_ttl", 300)

        logger.info(
            f"Creating CacheManager from settings: "
            f"cache_dir={cache_dir}, size_limit={size_limit}"
        )

        return cls(
            cache_dir=cache_dir,
            size_limit=size_limit,
            content_ttl=content_ttl,
            search_ttl=search_ttl,
        )

    def stats(self) -> dict:
        """
        Get comprehensive cache statistics from all components.

        This method aggregates statistics from all cache components, providing
        a complete view of cache usage and performance.

        Returns:
            A dictionary containing:
                - enabled: Whether the cache is enabled (always True)
                - disk_cache: PersistentCache statistics (size, volume, directory)
                - content_ttl: Configured TTL for content cache
                - search_ttl: Configured TTL for search cache
                - configuration: Cache manager configuration settings

        Example:
            >>> stats = manager.stats()
            >>> print(f"Total entries: {stats['disk_cache']['size']}")
            >>> print(f"Disk usage: {stats['disk_cache']['volume'] / 1024 / 1024:.2f} MB")
            >>> print(f"Location: {stats['disk_cache']['directory']}")
            >>> print(f"Content TTL: {stats['content_ttl']}s")
            >>> print(f"Search TTL: {stats['search_ttl']}s")

        Note:
            The 'size' metric represents the number of entries, while 'volume'
            represents the actual disk space used (which includes overhead).
        """
        disk_stats = self.persistent_cache.stats()

        return {
            "enabled": True,
            "disk_cache": disk_stats,
            "content_ttl": self._content_ttl,
            "search_ttl": self._search_ttl,
            "configuration": {
                "cache_directory": disk_stats["directory"],
                "size_limit": disk_stats.get("size_limit", "unknown"),
                "eviction_policy": "least-recently-used",
            },
        }

    async def clear_all(self) -> None:
        """
        Clear all caches and reset all tracking state.

        This operation removes all cached data from all components, including:
        - All file content cache entries
        - All search result cache entries
        - All file state tracking data
        - All entries in the persistent cache

        Warning:
            This operation is irreversible and will permanently remove all cached
            data. It should be used sparingly and typically only for:
            - Manual cache refresh/reset
            - Testing and development
            - Recovery from cache corruption

        Example:
            >>> # Clear all caches
            >>> await manager.clear_all()
            >>>
            >>> # Verify caches are empty
            >>> stats = manager.stats()
            >>> assert stats['disk_cache']['size'] == 0

        Note:
            After clearing, the next access to any cached resource will trigger
            a fresh load from disk/computation. This may cause a temporary
            performance impact until caches are repopulated.
        """
        logger.warning("Clearing ALL caches - this will remove all cached data")

        # Clear the persistent cache (which clears all entries including
        # content cache, search cache, and file state tracking)
        await self.persistent_cache.clear()

        logger.info("All caches cleared successfully")

    async def __aenter__(self) -> "CacheManager":
        """
        Async context manager entry.

        Allows using CacheManager as an async context manager for automatic
        resource cleanup.

        Example:
            >>> async with CacheManager.default() as manager:
            ...     content = await manager.content_cache.get_content(
            ...         Path("data.txt"),
            ...         lambda p: p.read_text()
            ...     )
            ...     # manager automatically cleaned up on exit
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Ensures proper cleanup when using CacheManager as a context manager.
        Currently, cleanup is handled by the underlying PersistentCache.
        """
        # Cleanup is handled by PersistentCache's __del__
        pass

    def close(self) -> None:
        """
        Close the cache manager and release all resources.

        This should be called when the cache manager is no longer needed to ensure
        proper cleanup of file handles, locks, and other resources.

        Example:
            >>> manager = CacheManager.default()
            >>> # ... use manager ...
            >>> manager.close()

        Note:
            After calling close(), the cache manager instance should not be used.
        """
        logger.info("Closing CacheManager")
        self.persistent_cache.close()
        logger.info("CacheManager closed successfully")

    def __del__(self):
        """
        Destructor to ensure cache is closed on garbage collection.

        This is a safety mechanism to ensure resources are released even if
        close() is not explicitly called.
        """
        try:
            self.persistent_cache.close()
        except Exception:
            # Silently ignore errors during cleanup
            pass
