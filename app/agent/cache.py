"""
TTL-based cache for tool execution results.
Provides caching functionality to avoid duplicate command executions.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING
import hashlib
import json
import threading

if TYPE_CHECKING:
    from app.sandbox.executor import ExecutionResult


class ToolResultCache:
    """
    TTL-based cache for tool execution results.

    Features:
    - TTL (time-to-live) based expiration
    - LRU eviction when max size is reached
    - Thread-safe operations
    - Path-based invalidation
    - Cache statistics tracking
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of entries in the cache
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.cache: Dict[str, dict] = {}
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _generate_key(self, command: List[str]) -> str:
        """
        Generate cache key from command.

        Args:
            command: The command as a list of strings

        Returns:
            A hash string that uniquely identifies the command
        """
        # Create a canonical string representation of the command
        command_str = json.dumps(command, sort_keys=True)
        # Generate SHA-256 hash for the key
        return hashlib.sha256(command_str.encode('utf-8')).hexdigest()

    def _is_valid(self, entry: dict) -> bool:
        """
        Check if cache entry is still valid (not expired).

        Args:
            entry: The cache entry to check

        Returns:
            True if the entry is still valid, False otherwise
        """
        if 'timestamp' not in entry:
            return False

        expiration_time = entry['timestamp'] + self.ttl
        return datetime.now() < expiration_time

    def _evict_expired(self) -> None:
        """Remove all expired entries from the cache."""
        expired_keys = [
            key for key, entry in self.cache.items()
            if not self._is_valid(entry)
        ]
        for key in expired_keys:
            del self.cache[key]

    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self.cache:
            return

        # Find the oldest entry by last_accessed timestamp
        oldest_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].get('last_accessed', datetime.min)
        )
        del self.cache[oldest_key]

    def get(self, command: List[str]) -> Optional["ExecutionResult"]:
        """
        Get cached result if exists and valid.

        Args:
            command: The command to look up

        Returns:
            The cached ExecutionResult if found and valid, None otherwise
        """
        key = self._generate_key(command)

        with self._lock:
            if key not in self.cache:
                self._misses += 1
                return None

            entry = self.cache[key]

            if not self._is_valid(entry):
                # Entry expired, remove it
                del self.cache[key]
                self._misses += 1
                return None

            # Update last accessed time for LRU
            entry['last_accessed'] = datetime.now()
            self._hits += 1

            return entry['result']

    def set(self, command: List[str], result: "ExecutionResult") -> None:
        """
        Cache execution result with LRU eviction.

        Args:
            command: The command that was executed
            result: The execution result to cache
        """
        key = self._generate_key(command)
        now = datetime.now()

        with self._lock:
            # First, evict expired entries
            self._evict_expired()

            # If we're at max capacity and this is a new entry, evict LRU
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()

            # Store the entry
            self.cache[key] = {
                'result': result,
                'command': command,
                'timestamp': now,
                'last_accessed': now,
            }

    def _is_path_related(self, target_path: Path, arg: str) -> bool:
        """
        Check if an argument path should be invalidated when target_path changes.

        Uses proper path boundary checking instead of substring matching to avoid
        false positives like '/data' matching '/database'.

        Invalidation rules:
        - If target is a file: invalidate commands that reference that exact file
        - If target is a directory: invalidate commands referencing files under it

        Args:
            target_path: The resolved target path that changed
            arg: The command argument to check

        Returns:
            True if the cached command should be invalidated
        """
        try:
            arg_path = Path(arg)
            # Try to resolve if it looks like a path (has separators or is relative)
            if '/' in arg or arg.startswith('.'):
                arg_path = arg_path.resolve()
            else:
                # Single word args are likely not paths (e.g., grep patterns)
                return False

            # Check if paths are equal (exact match)
            if arg_path == target_path:
                return True

            # Check if arg_path is under target_path (target is a parent directory)
            # Example: invalidating ./data/ should invalidate ./data/file.txt
            try:
                arg_path.relative_to(target_path)
                return True
            except ValueError:
                pass

            # NOTE: We intentionally do NOT check if target_path is under arg_path
            # Invalidating a specific file should NOT invalidate commands on parent dirs
            # Example: invalidating ./data/file.txt should NOT invalidate ls ./data/

            return False
        except (OSError, ValueError):
            # Not a valid path, skip
            return False

    def invalidate_path(self, path: str) -> int:
        """
        Invalidate all cache entries related to a path.

        This is useful when a file might have been modified and cached
        results for commands involving that file should be cleared.

        Uses proper path boundary checking to avoid false positives.
        For example, invalidating '/data' will NOT invalidate '/database'.

        Args:
            path: The path to invalidate entries for

        Returns:
            Number of entries invalidated
        """
        invalidated_count = 0
        target_path = Path(path).resolve()

        with self._lock:
            keys_to_remove = []

            for key, entry in self.cache.items():
                command = entry.get('command', [])
                # Check if any command argument is a related path
                # Skip first element (command name like 'grep', 'cat', etc.)
                for arg in command[1:]:
                    if self._is_path_related(target_path, str(arg)):
                        keys_to_remove.append(key)
                        break

            for key in keys_to_remove:
                del self.cache[key]
                invalidated_count += 1

        return invalidated_count

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self.cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """
        Return cache statistics.

        Returns:
            Dictionary containing cache statistics:
            - size: Current number of entries
            - max_size: Maximum allowed entries
            - hits: Number of cache hits
            - misses: Number of cache misses
            - hit_rate: Ratio of hits to total requests (0-1)
            - ttl_seconds: TTL in seconds
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'ttl_seconds': self.ttl.total_seconds(),
            }
