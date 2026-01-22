"""
Cached sandbox executor for the Filesystem Agent.
Extends SandboxExecutor with result caching to avoid duplicate executions.
"""

import logging
from pathlib import Path
from typing import List, Optional

from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.agent.cache import ToolResultCache

logger = logging.getLogger(__name__)


class CachedSandboxExecutor(SandboxExecutor):
    """
    Sandbox executor with result caching.

    Extends SandboxExecutor to cache successful command results,
    avoiding redundant executions of the same commands.
    """

    def __init__(
        self,
        root_path: Path,
        timeout: int = 30,
        max_output_size: int = 1024 * 1024,
        max_file_size: int = 10 * 1024 * 1024,
        enabled: bool = True,
        cache_enabled: bool = True,
        cache_ttl: int = 300,
        cache_max_size: int = 100,
    ):
        """
        Initialize the cached sandbox executor.

        Args:
            root_path: The root directory for sandboxed operations
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in bytes (default: 1MB)
            max_file_size: Maximum file size for cat operations in bytes (default: 10MB)
            enabled: If False, sandbox checks are bypassed (for testing only)
            cache_enabled: If True, enable result caching
            cache_ttl: Cache TTL in seconds (default: 300 = 5 minutes)
            cache_max_size: Maximum number of cached entries (default: 100)
        """
        super().__init__(
            root_path=root_path,
            timeout=timeout,
            max_output_size=max_output_size,
            max_file_size=max_file_size,
            enabled=enabled,
        )

        self.cache_enabled = cache_enabled
        self.cache: Optional[ToolResultCache] = None

        if cache_enabled:
            self.cache = ToolResultCache(
                max_size=cache_max_size,
                ttl_seconds=cache_ttl,
            )
            logger.info(
                f"Initialized cache with max_size={cache_max_size}, ttl={cache_ttl}s"
            )

    async def execute(self, command: List[str]) -> ExecutionResult:
        """
        Execute a command with cache check.

        If caching is enabled, checks the cache first. If the command
        result is cached and valid, returns the cached result.
        Otherwise, executes the command and caches successful results.

        Args:
            command: The command as a list of strings

        Returns:
            ExecutionResult with the command output
        """
        # If cache is disabled, execute directly
        if not self.cache_enabled or self.cache is None:
            return await super().execute(command)

        # Check cache first
        cached_result = self.cache.get(command)
        if cached_result is not None:
            logger.info(f"Cache HIT for command: {' '.join(command[:3])}...")
            return cached_result

        logger.debug(f"Cache MISS for command: {' '.join(command[:3])}...")

        # Execute the command
        result = await super().execute(command)

        # Only cache successful results
        if result.success:
            self.cache.set(command, result)
            logger.debug(f"Cached result for command: {' '.join(command[:3])}...")

        return result

    def invalidate_path(self, path: str) -> int:
        """
        Invalidate all cache entries related to a path.

        Args:
            path: The path to invalidate entries for

        Returns:
            Number of entries invalidated
        """
        if self.cache_enabled and self.cache is not None:
            count = self.cache.invalidate_path(path)
            if count > 0:
                logger.info(f"Invalidated {count} cache entries for path: {path}")
            return count
        return 0

    def clear_cache(self) -> None:
        """Clear all cache entries."""
        if self.cache_enabled and self.cache is not None:
            self.cache.clear()
            logger.info("Cache cleared")

    def cache_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics, or empty dict if cache is disabled
        """
        if self.cache_enabled and self.cache is not None:
            return self.cache.stats()
        return {
            'enabled': False,
            'size': 0,
            'max_size': 0,
            'hits': 0,
            'misses': 0,
            'hit_rate': 0.0,
        }
