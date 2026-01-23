"""
Tests for the CachedSandboxExecutor.
"""

import pytest
from pathlib import Path
import tempfile

from app.sandbox.cached_executor import CachedSandboxExecutor
from app.sandbox.executor import ExecutionResult


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Resolve to handle macOS symlinks (/var -> /private/var)
        test_dir = Path(tmpdir).resolve()
        (test_dir / "test.txt").write_text("Hello, World!\nLine 2\nLine 3")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("Nested content")
        yield test_dir


@pytest.fixture
def cached_executor(temp_data_dir):
    """Create a cached sandbox executor for testing."""
    return CachedSandboxExecutor(
        root_path=temp_data_dir,
        timeout=10,
        enabled=True,
        cache_enabled=True,
        cache_ttl=300,
        cache_max_size=10,
    )


@pytest.fixture
def uncached_executor(temp_data_dir):
    """Create a non-cached sandbox executor for testing."""
    return CachedSandboxExecutor(
        root_path=temp_data_dir,
        timeout=10,
        enabled=True,
        cache_enabled=False,
    )


class TestCachedExecution:
    """Tests for cached command execution."""

    @pytest.mark.asyncio
    async def test_first_execution_not_cached(self, cached_executor):
        """Test that first execution is not from cache."""
        result = await cached_executor.execute(["ls", "."])

        assert result.success
        stats = cached_executor.cache_stats()
        # First execution should be a miss
        assert stats['misses'] == 1
        assert stats['hits'] == 0

    @pytest.mark.asyncio
    async def test_second_execution_from_cache(self, cached_executor):
        """Test that second execution of same command is from cache."""
        command = ["ls", "."]

        # First execution
        result1 = await cached_executor.execute(command)
        assert result1.success

        # Second execution - should be from cache
        result2 = await cached_executor.execute(command)
        assert result2.success

        stats = cached_executor.cache_stats()
        assert stats['misses'] == 1
        assert stats['hits'] == 1

        # Results should be identical
        assert result1.stdout == result2.stdout
        assert result1.return_code == result2.return_code

    @pytest.mark.asyncio
    async def test_different_commands_not_cached(self, cached_executor):
        """Test that different commands are executed separately."""
        # Execute two different commands
        result1 = await cached_executor.execute(["ls", "."])
        result2 = await cached_executor.execute(["cat", "test.txt"])

        assert result1.success
        assert result2.success

        stats = cached_executor.cache_stats()
        # Both should be misses
        assert stats['misses'] == 2
        assert stats['hits'] == 0

    @pytest.mark.asyncio
    async def test_failed_commands_not_cached(self, cached_executor):
        """Test that failed commands are not cached."""
        command = ["cat", "nonexistent_file.txt"]

        # First execution - should fail
        result1 = await cached_executor.execute(command)
        assert not result1.success

        # Second execution - should also fail and not be from cache
        result2 = await cached_executor.execute(command)
        assert not result2.success

        stats = cached_executor.cache_stats()
        # Both should be misses (failed results not cached)
        assert stats['misses'] == 2
        assert stats['hits'] == 0

    @pytest.mark.asyncio
    async def test_cache_disabled(self, uncached_executor):
        """Test that caching can be disabled."""
        command = ["ls", "."]

        # Execute twice
        await uncached_executor.execute(command)
        await uncached_executor.execute(command)

        # Stats should show cache is disabled
        stats = uncached_executor.cache_stats()
        assert stats.get('enabled') is False or stats['size'] == 0


class TestCacheBypass:
    """Tests for cache bypass functionality."""

    @pytest.mark.asyncio
    async def test_cache_stats_when_disabled(self, uncached_executor):
        """Test cache stats when cache is disabled."""
        stats = uncached_executor.cache_stats()

        assert stats['enabled'] is False
        assert stats['size'] == 0
        assert stats['hits'] == 0
        assert stats['misses'] == 0


class TestCacheInvalidation:
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_path(self, cached_executor):
        """Test that path invalidation works."""
        # Execute command to cache it (use ./ prefix for proper path recognition)
        command = ["cat", "./test.txt"]
        await cached_executor.execute(command)

        stats = cached_executor.cache_stats()
        assert stats['size'] == 1

        # Invalidate the path
        count = cached_executor.invalidate_path("./test.txt")
        assert count == 1

        # Cache should be empty
        stats = cached_executor.cache_stats()
        assert stats['size'] == 0

    @pytest.mark.asyncio
    async def test_invalidate_does_not_affect_other_paths(self, cached_executor):
        """Test that invalidation only affects matching paths."""
        # Cache multiple commands (use ./ prefix for proper path recognition)
        await cached_executor.execute(["cat", "./test.txt"])
        await cached_executor.execute(["ls", "."])

        stats = cached_executor.cache_stats()
        assert stats['size'] == 2

        # Invalidate only test.txt
        cached_executor.invalidate_path("./test.txt")

        stats = cached_executor.cache_stats()
        assert stats['size'] == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self, cached_executor):
        """Test that cache can be cleared."""
        # Cache multiple commands
        await cached_executor.execute(["cat", "test.txt"])
        await cached_executor.execute(["ls", "."])

        stats = cached_executor.cache_stats()
        assert stats['size'] == 2

        # Clear the cache
        cached_executor.clear_cache()

        stats = cached_executor.cache_stats()
        assert stats['size'] == 0


class TestCacheLogging:
    """Tests for cache hit logging."""

    @pytest.mark.asyncio
    async def test_cache_hit_logged(self, cached_executor, caplog):
        """Test that cache hits are logged."""
        import logging

        caplog.set_level(logging.INFO)

        command = ["ls", "."]

        # First execution
        await cached_executor.execute(command)

        # Second execution - should be a hit
        await cached_executor.execute(command)

        # Check that cache hit was logged
        assert any("Cache HIT" in record.message for record in caplog.records)


class TestCacheWithSandboxFeatures:
    """Tests for cache interaction with sandbox features."""

    @pytest.mark.asyncio
    async def test_cached_result_preserves_all_fields(self, cached_executor):
        """Test that cached results preserve all ExecutionResult fields."""
        command = ["cat", "test.txt"]

        # First execution
        result1 = await cached_executor.execute(command)

        # Second execution from cache
        result2 = await cached_executor.execute(command)

        # All fields should be preserved
        assert result1.success == result2.success
        assert result1.stdout == result2.stdout
        assert result1.stderr == result2.stderr
        assert result1.return_code == result2.return_code
        assert result1.command == result2.command
        assert result1.error == result2.error

    @pytest.mark.asyncio
    async def test_cache_with_command_arguments(self, cached_executor):
        """Test that cache correctly differentiates command arguments."""
        # Execute head with different line counts
        result1 = await cached_executor.execute(["head", "-n", "1", "test.txt"])
        result2 = await cached_executor.execute(["head", "-n", "2", "test.txt"])

        # Results should be different
        assert result1.stdout != result2.stdout

        # Both should be cache misses
        stats = cached_executor.cache_stats()
        assert stats['misses'] == 2

    @pytest.mark.asyncio
    async def test_cache_with_grep_patterns(self, cached_executor):
        """Test that cache correctly handles grep patterns."""
        # Execute grep with different patterns
        await cached_executor.execute(["grep", "Hello", "test.txt"])
        await cached_executor.execute(["grep", "Line", "test.txt"])

        # Both should be cache misses (different patterns)
        stats = cached_executor.cache_stats()
        assert stats['misses'] == 2

        # Execute first pattern again - should be a hit
        await cached_executor.execute(["grep", "Hello", "test.txt"])

        stats = cached_executor.cache_stats()
        assert stats['hits'] == 1


class TestCacheConfiguration:
    """Tests for cache configuration options."""

    @pytest.mark.asyncio
    async def test_custom_ttl(self, temp_data_dir):
        """Test that custom TTL is respected."""
        import time

        # Create executor with very short TTL
        executor = CachedSandboxExecutor(
            root_path=temp_data_dir,
            timeout=10,
            enabled=True,
            cache_enabled=True,
            cache_ttl=1,  # 1 second TTL
            cache_max_size=10,
        )

        command = ["ls", "."]

        # First execution
        await executor.execute(command)

        # Immediate second execution - should be a hit
        await executor.execute(command)

        stats = executor.cache_stats()
        assert stats['hits'] == 1

        # Wait for TTL to expire
        time.sleep(1.1)

        # Third execution - should be a miss (expired)
        await executor.execute(command)

        stats = executor.cache_stats()
        assert stats['misses'] == 2

    @pytest.mark.asyncio
    async def test_custom_max_size(self, temp_data_dir):
        """Test that custom max_size is respected."""
        # Create executor with small max size
        executor = CachedSandboxExecutor(
            root_path=temp_data_dir,
            timeout=10,
            enabled=True,
            cache_enabled=True,
            cache_ttl=300,
            cache_max_size=2,  # Only 2 entries
        )

        # Execute 3 different commands
        await executor.execute(["ls", "."])
        await executor.execute(["cat", "test.txt"])
        await executor.execute(["wc", "-l", "test.txt"])

        # Only 2 entries should be cached (oldest evicted)
        stats = executor.cache_stats()
        assert stats['size'] == 2
        assert stats['max_size'] == 2


class TestCacheInheritance:
    """Tests to verify CachedSandboxExecutor properly inherits from SandboxExecutor."""

    @pytest.mark.asyncio
    async def test_command_validation_still_works(self, cached_executor):
        """Test that command validation is inherited."""
        # Try to execute a disallowed command
        result = await cached_executor.execute(["rm", "test.txt"])

        assert not result.success
        assert result.error == "COMMAND_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_path_traversal_prevention_still_works(self, cached_executor):
        """Test that path traversal prevention is inherited."""
        result = await cached_executor.execute(["cat", "../../../etc/passwd"])

        assert not result.success
        assert result.error == "PATH_TRAVERSAL"

    @pytest.mark.asyncio
    async def test_allowed_commands_work(self, cached_executor):
        """Test that all allowed commands work through the cached executor."""
        # Test various allowed commands
        commands = [
            ["ls", "."],
            ["cat", "test.txt"],
            ["head", "-n", "1", "test.txt"],
            ["tail", "-n", "1", "test.txt"],
            ["wc", "-l", "test.txt"],
            ["find", ".", "-name", "*.txt"],
        ]

        for command in commands:
            result = await cached_executor.execute(command)
            assert result.success, f"Command {command} failed: {result.stderr}"
