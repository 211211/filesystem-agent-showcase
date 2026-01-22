"""Tests for the PersistentCache implementation."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.cache.disk_cache import PersistentCache


@pytest.fixture
async def temp_cache():
    """Create a temporary cache for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = PersistentCache(cache_dir=tmpdir, size_limit=1024 * 1024)  # 1MB
        yield cache
        cache.close()


class TestPersistentCache:
    """Test suite for PersistentCache."""

    async def test_set_and_get(self, temp_cache):
        """Test basic set and get operations."""
        await temp_cache.set("test_key", "test_value")
        result = await temp_cache.get("test_key")
        assert result == "test_value"

    async def test_get_nonexistent_key(self, temp_cache):
        """Test getting a key that doesn't exist."""
        result = await temp_cache.get("nonexistent")
        assert result is None

    async def test_delete_existing_key(self, temp_cache):
        """Test deleting an existing key."""
        await temp_cache.set("key_to_delete", "value")
        deleted = await temp_cache.delete("key_to_delete")
        assert deleted is True
        result = await temp_cache.get("key_to_delete")
        assert result is None

    async def test_delete_nonexistent_key(self, temp_cache):
        """Test deleting a key that doesn't exist."""
        deleted = await temp_cache.delete("nonexistent")
        assert deleted is False

    async def test_clear(self, temp_cache):
        """Test clearing the cache."""
        await temp_cache.set("key1", "value1")
        await temp_cache.set("key2", "value2")
        await temp_cache.clear()

        assert await temp_cache.get("key1") is None
        assert await temp_cache.get("key2") is None

        stats = temp_cache.stats()
        assert stats["size"] == 0

    async def test_stats(self, temp_cache):
        """Test cache statistics."""
        await temp_cache.set("key1", "value1")
        await temp_cache.set("key2", "value2")

        stats = temp_cache.stats()
        assert stats["size"] == 2
        assert stats["volume"] > 0
        assert "directory" in stats

    async def test_expiration(self, temp_cache):
        """Test key expiration."""
        await temp_cache.set("expiring_key", "value", expire=0.1)  # 100ms

        # Should exist immediately
        result = await temp_cache.get("expiring_key")
        assert result == "value"

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should be gone
        result = await temp_cache.get("expiring_key")
        assert result is None

    async def test_persistent_across_instances(self):
        """Test that cache persists across different instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create first cache instance
            cache1 = PersistentCache(cache_dir=tmpdir)
            await cache1.set("persistent_key", "persistent_value")
            cache1.close()

            # Create second cache instance with same directory
            cache2 = PersistentCache(cache_dir=tmpdir)
            result = await cache2.get("persistent_key")
            assert result == "persistent_value"
            cache2.close()

    async def test_async_context_manager(self):
        """Test using the cache as an async context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async with PersistentCache(cache_dir=tmpdir) as cache:
                await cache.set("context_key", "context_value")
                result = await cache.get("context_key")
                assert result == "context_value"

    async def test_concurrent_operations(self, temp_cache):
        """Test concurrent cache operations."""
        async def set_value(key: str, value: str):
            await temp_cache.set(key, value)

        async def get_value(key: str):
            return await temp_cache.get(key)

        # Set values concurrently
        await asyncio.gather(
            set_value("key1", "value1"),
            set_value("key2", "value2"),
            set_value("key3", "value3"),
        )

        # Get values concurrently
        results = await asyncio.gather(
            get_value("key1"),
            get_value("key2"),
            get_value("key3"),
        )

        assert results == ["value1", "value2", "value3"]

    async def test_complex_data_types(self, temp_cache):
        """Test caching complex data types."""
        # Test dictionary
        await temp_cache.set("dict_key", {"nested": {"data": [1, 2, 3]}})
        result = await temp_cache.get("dict_key")
        assert result == {"nested": {"data": [1, 2, 3]}}

        # Test list
        await temp_cache.set("list_key", [1, 2, 3, "four", {"five": 5}])
        result = await temp_cache.get("list_key")
        assert result == [1, 2, 3, "four", {"five": 5}]

    async def test_overwrite_existing_key(self, temp_cache):
        """Test overwriting an existing key."""
        await temp_cache.set("key", "original_value")
        await temp_cache.set("key", "new_value")
        result = await temp_cache.get("key")
        assert result == "new_value"
