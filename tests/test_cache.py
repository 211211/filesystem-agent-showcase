"""
Tests for the ToolResultCache.
"""

import pytest
from datetime import datetime, timedelta
import time

from app.agent.cache import ToolResultCache
from app.sandbox.executor import ExecutionResult


@pytest.fixture
def cache():
    """Create a cache with short TTL for testing."""
    return ToolResultCache(max_size=5, ttl_seconds=2)


@pytest.fixture
def sample_result():
    """Create a sample ExecutionResult for testing."""
    return ExecutionResult(
        success=True,
        stdout="Hello, World!",
        stderr="",
        return_code=0,
        command="cat test.txt",
    )


@pytest.fixture
def failed_result():
    """Create a failed ExecutionResult for testing."""
    return ExecutionResult(
        success=False,
        stdout="",
        stderr="File not found",
        return_code=1,
        command="cat nonexistent.txt",
        error="FileNotFoundError",
    )


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_same_command_same_key(self, cache):
        """Test that the same command generates the same key."""
        command = ["cat", "test.txt"]
        key1 = cache._generate_key(command)
        key2 = cache._generate_key(command)
        assert key1 == key2

    def test_different_command_different_key(self, cache):
        """Test that different commands generate different keys."""
        key1 = cache._generate_key(["cat", "test.txt"])
        key2 = cache._generate_key(["cat", "other.txt"])
        assert key1 != key2

    def test_order_matters(self, cache):
        """Test that argument order matters for key generation."""
        key1 = cache._generate_key(["grep", "pattern", "file.txt"])
        key2 = cache._generate_key(["grep", "file.txt", "pattern"])
        assert key1 != key2

    def test_key_is_string(self, cache):
        """Test that generated key is a string."""
        key = cache._generate_key(["ls", "-la"])
        assert isinstance(key, str)
        # Should be a SHA-256 hash (64 hex characters)
        assert len(key) == 64


class TestCacheHitMiss:
    """Tests for cache hit and miss behavior."""

    def test_cache_miss_on_empty_cache(self, cache):
        """Test cache miss when cache is empty."""
        result = cache.get(["cat", "test.txt"])
        assert result is None

    def test_cache_hit_after_set(self, cache, sample_result):
        """Test cache hit after setting a value."""
        command = ["cat", "test.txt"]
        cache.set(command, sample_result)

        result = cache.get(command)
        assert result is not None
        assert result.success == sample_result.success
        assert result.stdout == sample_result.stdout

    def test_cache_miss_for_different_command(self, cache, sample_result):
        """Test cache miss when querying a different command."""
        cache.set(["cat", "test.txt"], sample_result)

        result = cache.get(["cat", "other.txt"])
        assert result is None

    def test_stats_track_hits_and_misses(self, cache, sample_result):
        """Test that stats track hits and misses correctly."""
        command = ["cat", "test.txt"]

        # Miss
        cache.get(command)
        stats = cache.stats()
        assert stats['misses'] == 1
        assert stats['hits'] == 0

        # Set and hit
        cache.set(command, sample_result)
        cache.get(command)

        stats = cache.stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0.5


class TestCacheTTL:
    """Tests for cache TTL expiration."""

    def test_entry_valid_before_ttl(self, cache, sample_result):
        """Test that entry is valid before TTL expires."""
        command = ["cat", "test.txt"]
        cache.set(command, sample_result)

        # Immediately should be valid
        result = cache.get(command)
        assert result is not None

    def test_entry_expires_after_ttl(self):
        """Test that entry expires after TTL."""
        # Create cache with very short TTL
        cache = ToolResultCache(max_size=5, ttl_seconds=1)
        sample_result = ExecutionResult(
            success=True,
            stdout="test",
            stderr="",
            return_code=0,
            command="test",
        )

        command = ["cat", "test.txt"]
        cache.set(command, sample_result)

        # Should be valid immediately
        assert cache.get(command) is not None

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should be expired now
        result = cache.get(command)
        assert result is None

    def test_is_valid_checks_timestamp(self, cache):
        """Test _is_valid method checks timestamp correctly."""
        # Valid entry
        valid_entry = {
            'timestamp': datetime.now(),
            'result': None,
        }
        assert cache._is_valid(valid_entry) is True

        # Expired entry
        expired_entry = {
            'timestamp': datetime.now() - timedelta(seconds=10),
            'result': None,
        }
        assert cache._is_valid(expired_entry) is False

        # Entry without timestamp
        invalid_entry = {'result': None}
        assert cache._is_valid(invalid_entry) is False


class TestLRUEviction:
    """Tests for LRU eviction when max_size is reached."""

    def test_eviction_when_max_size_reached(self):
        """Test that oldest entry is evicted when max size is reached."""
        cache = ToolResultCache(max_size=3, ttl_seconds=300)

        # Add 3 entries
        for i in range(3):
            result = ExecutionResult(
                success=True,
                stdout=f"output {i}",
                stderr="",
                return_code=0,
                command=f"cmd{i}",
            )
            cache.set([f"cmd{i}"], result)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # All 3 should be present
        assert cache.stats()['size'] == 3

        # Add a 4th entry
        result = ExecutionResult(
            success=True,
            stdout="output 3",
            stderr="",
            return_code=0,
            command="cmd3",
        )
        cache.set(["cmd3"], result)

        # Should still be 3 (one was evicted)
        assert cache.stats()['size'] == 3

        # The oldest entry (cmd0) should have been evicted
        assert cache.get(["cmd0"]) is None

        # Newer entries should still be present
        assert cache.get(["cmd1"]) is not None
        assert cache.get(["cmd2"]) is not None
        assert cache.get(["cmd3"]) is not None

    def test_access_updates_lru_order(self):
        """Test that accessing an entry updates its LRU order."""
        cache = ToolResultCache(max_size=3, ttl_seconds=300)

        # Add 3 entries
        for i in range(3):
            result = ExecutionResult(
                success=True,
                stdout=f"output {i}",
                stderr="",
                return_code=0,
                command=f"cmd{i}",
            )
            cache.set([f"cmd{i}"], result)
            time.sleep(0.01)

        # Access cmd0 to make it recently used
        cache.get(["cmd0"])

        # Add a 4th entry - should evict cmd1 (oldest not-recently-used)
        result = ExecutionResult(
            success=True,
            stdout="output 3",
            stderr="",
            return_code=0,
            command="cmd3",
        )
        cache.set(["cmd3"], result)

        # cmd0 should still be present (was accessed recently)
        assert cache.get(["cmd0"]) is not None

        # cmd1 should have been evicted
        assert cache.get(["cmd1"]) is None


class TestPathInvalidation:
    """Tests for path-based cache invalidation."""

    def test_invalidate_single_path(self, cache):
        """Test invalidating entries for a single path."""
        # Add entries for different files
        for filename in ["test.txt", "other.txt", "data.txt"]:
            result = ExecutionResult(
                success=True,
                stdout=f"content of {filename}",
                stderr="",
                return_code=0,
                command=f"cat {filename}",
            )
            cache.set(["cat", filename], result)

        # Verify all are cached
        assert cache.get(["cat", "test.txt"]) is not None
        assert cache.get(["cat", "other.txt"]) is not None

        # Invalidate entries for test.txt
        count = cache.invalidate_path("test.txt")

        # Should have invalidated 1 entry
        assert count == 1

        # test.txt entry should be gone
        assert cache.get(["cat", "test.txt"]) is None

        # Other entries should still be present
        assert cache.get(["cat", "other.txt"]) is not None

    def test_invalidate_partial_path_match(self, cache):
        """Test that invalidation matches partial paths."""
        # Add entries with nested paths
        for path in ["data/file1.txt", "data/file2.txt", "other/file.txt"]:
            result = ExecutionResult(
                success=True,
                stdout=f"content of {path}",
                stderr="",
                return_code=0,
                command=f"cat {path}",
            )
            cache.set(["cat", path], result)

        # Invalidate all entries containing "data/"
        count = cache.invalidate_path("data/")

        # Should have invalidated 2 entries
        assert count == 2

        # data/ entries should be gone
        assert cache.get(["cat", "data/file1.txt"]) is None
        assert cache.get(["cat", "data/file2.txt"]) is None

        # other/ entry should still be present
        assert cache.get(["cat", "other/file.txt"]) is not None

    def test_invalidate_returns_zero_for_no_match(self, cache, sample_result):
        """Test that invalidation returns 0 when nothing matches."""
        cache.set(["cat", "test.txt"], sample_result)

        count = cache.invalidate_path("nonexistent.txt")
        assert count == 0

        # Original entry should still be present
        assert cache.get(["cat", "test.txt"]) is not None


class TestClearFunctionality:
    """Tests for cache clear functionality."""

    def test_clear_removes_all_entries(self, cache, sample_result):
        """Test that clear removes all cache entries."""
        # Add multiple entries
        for i in range(3):
            cache.set([f"cmd{i}"], sample_result)

        assert cache.stats()['size'] == 3

        # Clear the cache
        cache.clear()

        assert cache.stats()['size'] == 0

        # All entries should be gone
        for i in range(3):
            assert cache.get([f"cmd{i}"]) is None

    def test_clear_resets_stats(self, cache, sample_result):
        """Test that clear resets hit/miss statistics."""
        command = ["cat", "test.txt"]

        # Generate some hits and misses
        cache.get(command)  # miss
        cache.set(command, sample_result)
        cache.get(command)  # hit

        stats_before = cache.stats()
        assert stats_before['hits'] == 1
        assert stats_before['misses'] == 1

        # Clear the cache
        cache.clear()

        stats_after = cache.stats()
        assert stats_after['hits'] == 0
        assert stats_after['misses'] == 0


class TestCacheStats:
    """Tests for cache statistics."""

    def test_stats_returns_correct_format(self, cache):
        """Test that stats returns all expected fields."""
        stats = cache.stats()

        assert 'size' in stats
        assert 'max_size' in stats
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'hit_rate' in stats
        assert 'ttl_seconds' in stats

    def test_stats_initial_values(self, cache):
        """Test initial stat values."""
        stats = cache.stats()

        assert stats['size'] == 0
        assert stats['max_size'] == 5
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['hit_rate'] == 0.0
        assert stats['ttl_seconds'] == 2.0

    def test_hit_rate_calculation(self, cache, sample_result):
        """Test hit rate calculation."""
        command = ["cat", "test.txt"]

        # 2 misses, 0 hits
        cache.get(command)
        cache.get(command)

        stats = cache.stats()
        assert stats['hit_rate'] == 0.0

        # Add entry and get 2 hits
        cache.set(command, sample_result)
        cache.get(command)
        cache.get(command)

        stats = cache.stats()
        # 2 hits / 4 total = 0.5
        assert stats['hit_rate'] == 0.5


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_access(self, cache, sample_result):
        """Test that concurrent access doesn't cause issues."""
        import threading

        errors = []

        def worker(worker_id):
            try:
                for i in range(100):
                    command = [f"cmd{worker_id}", str(i)]
                    cache.set(command, sample_result)
                    cache.get(command)
                    cache.invalidate_path(f"cmd{worker_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0
