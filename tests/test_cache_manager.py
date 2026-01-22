"""Tests for the CacheManager unified cache interface."""

import tempfile
from pathlib import Path

import pytest

from app.cache import CacheManager
from app.config import Settings


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create a CacheManager instance with temporary storage."""
    manager = CacheManager(
        cache_dir=temp_cache_dir,
        size_limit=10 * 1024 * 1024,  # 10MB for testing
        content_ttl=0,
        search_ttl=300,
    )
    yield manager
    manager.close()


class TestCacheManager:
    """Test suite for CacheManager class."""

    def test_initialization(self, temp_cache_dir):
        """Test CacheManager initializes all components correctly."""
        manager = CacheManager(
            cache_dir=temp_cache_dir,
            size_limit=10 * 1024 * 1024,
            content_ttl=0,
            search_ttl=300,
        )

        assert manager.persistent_cache is not None
        assert manager.file_state_tracker is not None
        assert manager.content_cache is not None
        assert manager.search_cache is not None
        assert manager._content_ttl == 0
        assert manager._search_ttl == 300

        manager.close()

    def test_default_initialization(self):
        """Test CacheManager.default() creates instance from settings."""
        settings = Settings(
            azure_openai_api_key="test-key",
            azure_openai_endpoint="https://test.openai.azure.com/",
            cache_directory="tmp/test_cache",
            cache_size_limit=1024 * 1024,  # 1MB
            cache_content_ttl=10,
            cache_search_ttl=60,
        )

        manager = CacheManager.default(settings)

        assert manager is not None
        assert manager._content_ttl == 10
        assert manager._search_ttl == 60

        manager.close()

    def test_stats(self, cache_manager):
        """Test stats() returns comprehensive cache statistics."""
        stats = cache_manager.stats()

        assert "disk_cache" in stats
        assert "content_ttl" in stats
        assert "search_ttl" in stats
        assert "configuration" in stats

        assert stats["content_ttl"] == 0
        assert stats["search_ttl"] == 300

        assert "size" in stats["disk_cache"]
        assert "volume" in stats["disk_cache"]
        assert "directory" in stats["disk_cache"]

        assert "cache_directory" in stats["configuration"]
        assert "size_limit" in stats["configuration"]
        assert "eviction_policy" in stats["configuration"]

    async def test_clear_all(self, cache_manager):
        """Test clear_all() removes all cached data."""
        # Add some data to the cache
        await cache_manager.persistent_cache.set("test_key", "test_value")

        # Verify data is cached
        stats_before = cache_manager.stats()
        assert stats_before["disk_cache"]["size"] > 0

        # Clear all caches
        await cache_manager.clear_all()

        # Verify cache is empty
        stats_after = cache_manager.stats()
        assert stats_after["disk_cache"]["size"] == 0

        # Verify data is gone
        value = await cache_manager.persistent_cache.get("test_key")
        assert value is None

    async def test_content_cache_integration(self, cache_manager, tmp_path):
        """Test ContentCache works through CacheManager."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Define a loader function
        async def load_content(path: Path) -> str:
            return path.read_text()

        # Get content through content cache
        content = await cache_manager.content_cache.get_content(
            test_file, load_content
        )

        assert content == "Hello, World!"

        # Verify it's cached (second call should hit cache)
        content2 = await cache_manager.content_cache.get_content(
            test_file, load_content
        )

        assert content2 == "Hello, World!"

    async def test_search_cache_integration(self, cache_manager, tmp_path):
        """Test SearchCache works through CacheManager."""
        # Create a test file (not directory) for the scope
        scope_file = tmp_path / "test_file.txt"
        scope_file.write_text("test content")

        # Cache a search result
        await cache_manager.search_cache.set_search_result(
            operation="grep",
            pattern="test",
            scope=scope_file,
            options={"case_sensitive": True},
            result="test_file.txt:1:test content",
            ttl=300,
        )

        # Retrieve cached result
        result = await cache_manager.search_cache.get_search_result(
            operation="grep",
            pattern="test",
            scope=scope_file,
            options={"case_sensitive": True},
        )

        assert result == "test_file.txt:1:test content"

    async def test_context_manager(self, temp_cache_dir):
        """Test CacheManager works as async context manager."""
        async with CacheManager(cache_dir=temp_cache_dir) as manager:
            assert manager is not None
            await manager.persistent_cache.set("key", "value")
            value = await manager.persistent_cache.get("key")
            assert value == "value"

        # Manager should be closed after exiting context

    def test_close(self, temp_cache_dir):
        """Test close() properly releases resources."""
        manager = CacheManager(cache_dir=temp_cache_dir)

        # Use the manager
        stats = manager.stats()
        assert stats is not None

        # Close it
        manager.close()

        # After closing, the manager should not be used
        # (we don't test this as it would cause errors)

    async def test_file_state_tracker_integration(self, cache_manager, tmp_path):
        """Test FileStateTracker works through CacheManager."""
        test_file = tmp_path / "state_test.txt"
        test_file.write_text("initial content")

        # Update state
        state = await cache_manager.file_state_tracker.update_state(test_file)

        assert state is not None
        assert state.size == len("initial content")

        # Check if file is stale (should be False since we just updated it)
        is_stale = await cache_manager.file_state_tracker.is_stale(test_file)
        assert is_stale is False

        # Modify the file
        test_file.write_text("modified content")

        # Check if file is stale (should be True now)
        is_stale = await cache_manager.file_state_tracker.is_stale(test_file)
        assert is_stale is True

    async def test_multiple_operations(self, cache_manager, tmp_path):
        """Test multiple cache operations work together correctly."""
        # Create test files
        file1 = tmp_path / "file1.txt"
        file1.write_text("content 1")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content 2")

        # Define loader
        async def loader(path: Path) -> str:
            return path.read_text()

        # Cache content for both files
        content1 = await cache_manager.content_cache.get_content(file1, loader)
        content2 = await cache_manager.content_cache.get_content(file2, loader)

        assert content1 == "content 1"
        assert content2 == "content 2"

        # Cache a search result (use file1 as scope instead of directory)
        await cache_manager.search_cache.set_search_result(
            operation="grep",
            pattern="content",
            scope=file1,
            options={},
            result="file1.txt:1:content 1",
            ttl=300,
        )

        # Get stats
        stats = cache_manager.stats()
        assert stats["disk_cache"]["size"] > 0

        # Clear everything
        await cache_manager.clear_all()

        # Verify cleared
        stats = cache_manager.stats()
        assert stats["disk_cache"]["size"] == 0
