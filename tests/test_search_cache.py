"""Tests for the SearchCache implementation."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.cache.disk_cache import PersistentCache
from app.cache.file_state import FileStateTracker
from app.cache.search_cache import SearchCache


@pytest.fixture
async def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def cache_components(temp_dir):
    """Create cache components for testing."""
    cache_dir = temp_dir / "cache"
    cache = PersistentCache(cache_dir=str(cache_dir), size_limit=1024 * 1024)  # 1MB
    tracker = FileStateTracker(cache)
    search_cache = SearchCache(cache, tracker)

    yield search_cache, cache, tracker

    cache.close()


@pytest.fixture
async def test_file(temp_dir):
    """Create a test file."""
    file_path = temp_dir / "test_file.txt"
    file_path.write_text("Hello, World!")
    return file_path


class TestSearchCache:
    """Test suite for SearchCache."""

    async def test_cache_miss_on_first_access(self, cache_components, temp_dir):
        """Test that first access results in cache miss."""
        search_cache, _, _ = cache_components

        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options={"case_sensitive": True}
        )

        assert result is None

    async def test_cache_hit_after_set(self, cache_components, temp_dir):
        """Test that cached result can be retrieved."""
        search_cache, _, _ = cache_components

        expected_result = "file.py:10:# TODO: fix this"
        options = {"case_sensitive": True}

        # Set cache
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options,
            result=expected_result,
            ttl=300
        )

        # Get from cache
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )

        assert result == expected_result

    async def test_deterministic_key_generation(self, cache_components, temp_dir):
        """Test that same parameters generate same cache key."""
        search_cache, _, _ = cache_components

        # Set cache with specific parameters
        options = {"case_sensitive": True, "max_results": 100}
        expected_result = "search result"

        await search_cache.set_search_result(
            operation="grep",
            pattern="ERROR",
            scope=temp_dir,
            options=options,
            result=expected_result
        )

        # Retrieve with same parameters (different order in options dict)
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="ERROR",
            scope=temp_dir,
            options={"max_results": 100, "case_sensitive": True}  # Different order
        )

        assert result == expected_result

    async def test_different_patterns_different_cache(self, cache_components, temp_dir):
        """Test that different patterns create separate cache entries."""
        search_cache, _, _ = cache_components
        options = {"case_sensitive": True}

        # Cache two different patterns
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options,
            result="TODO results"
        )

        await search_cache.set_search_result(
            operation="grep",
            pattern="FIXME",
            scope=temp_dir,
            options=options,
            result="FIXME results"
        )

        # Verify both are cached separately
        todo_result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )

        fixme_result = await search_cache.get_search_result(
            operation="grep",
            pattern="FIXME",
            scope=temp_dir,
            options=options
        )

        assert todo_result == "TODO results"
        assert fixme_result == "FIXME results"

    async def test_different_scopes_different_cache(self, cache_components, temp_dir):
        """Test that different scopes create separate cache entries."""
        search_cache, _, _ = cache_components

        dir1 = temp_dir / "dir1"
        dir2 = temp_dir / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        options = {"case_sensitive": True}

        # Cache same pattern in different scopes
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=dir1,
            options=options,
            result="dir1 results"
        )

        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=dir2,
            options=options,
            result="dir2 results"
        )

        # Verify both are cached separately
        dir1_result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=dir1,
            options=options
        )

        dir2_result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=dir2,
            options=options
        )

        assert dir1_result == "dir1 results"
        assert dir2_result == "dir2 results"

    async def test_file_modification_invalidates_cache(self, cache_components, test_file):
        """Test that modifying a file invalidates its cache."""
        search_cache, _, _ = cache_components
        options = {"case_sensitive": True}

        # Cache search result
        await search_cache.set_search_result(
            operation="grep",
            pattern="World",
            scope=test_file,
            options=options,
            result="test_file.txt:1:Hello, World!"
        )

        # Verify cache hit
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="World",
            scope=test_file,
            options=options
        )
        assert result is not None

        # Modify file
        test_file.write_text("Hello, Universe!")

        # Verify cache miss (file changed)
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="World",
            scope=test_file,
            options=options
        )
        assert result is None

    async def test_directory_modification_invalidates_cache(self, cache_components, temp_dir):
        """Test that directory modification invalidates cache."""
        search_cache, _, _ = cache_components
        options = {"case_sensitive": True}

        # Create a subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()

        # Cache search result
        await search_cache.set_search_result(
            operation="find",
            pattern="*.py",
            scope=subdir,
            options=options,
            result="file1.py\nfile2.py"
        )

        # Verify cache hit
        result = await search_cache.get_search_result(
            operation="find",
            pattern="*.py",
            scope=subdir,
            options=options
        )
        assert result is not None

        # Modify directory by adding a file
        (subdir / "new_file.txt").write_text("new content")

        # Verify cache miss (directory changed)
        result = await search_cache.get_search_result(
            operation="find",
            pattern="*.py",
            scope=subdir,
            options=options
        )
        assert result is None

    async def test_ttl_expiration(self, cache_components, temp_dir):
        """Test that cache entries expire after TTL."""
        search_cache, _, _ = cache_components
        options = {"case_sensitive": True}

        # Cache with short TTL
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options,
            result="cached result",
            ttl=0.1  # 100ms
        )

        # Should exist immediately
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )
        assert result == "cached result"

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should be expired
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )
        assert result is None

    async def test_invalidate_pattern(self, cache_components, temp_dir):
        """Test manual cache invalidation."""
        search_cache, _, _ = cache_components
        options = {"case_sensitive": True}

        # Cache result
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options,
            result="cached result"
        )

        # Verify cache hit
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )
        assert result == "cached result"

        # Manually invalidate
        deleted = await search_cache.invalidate_pattern(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )
        assert deleted is True

        # Verify cache miss
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options=options
        )
        assert result is None

    async def test_invalidate_nonexistent_pattern(self, cache_components, temp_dir):
        """Test invalidating a pattern that doesn't exist in cache."""
        search_cache, _, _ = cache_components

        deleted = await search_cache.invalidate_pattern(
            operation="grep",
            pattern="NONEXISTENT",
            scope=temp_dir,
            options={}
        )
        assert deleted is False

    async def test_concurrent_cache_operations(self, cache_components, temp_dir):
        """Test concurrent cache set and get operations."""
        search_cache, _, _ = cache_components

        async def cache_operation(pattern: str):
            options = {"case_sensitive": True}
            result = f"result for {pattern}"

            await search_cache.set_search_result(
                operation="grep",
                pattern=pattern,
                scope=temp_dir,
                options=options,
                result=result
            )

            return await search_cache.get_search_result(
                operation="grep",
                pattern=pattern,
                scope=temp_dir,
                options=options
            )

        # Run multiple operations concurrently
        results = await asyncio.gather(
            cache_operation("TODO"),
            cache_operation("FIXME"),
            cache_operation("HACK"),
        )

        assert results == [
            "result for TODO",
            "result for FIXME",
            "result for HACK",
        ]

    async def test_cache_with_empty_options(self, cache_components, temp_dir):
        """Test caching with empty options dictionary."""
        search_cache, _, _ = cache_components

        await search_cache.set_search_result(
            operation="find",
            pattern="*.py",
            scope=temp_dir,
            options={},
            result="file1.py\nfile2.py"
        )

        result = await search_cache.get_search_result(
            operation="find",
            pattern="*.py",
            scope=temp_dir,
            options={}
        )

        assert result == "file1.py\nfile2.py"

    async def test_cache_key_prefix(self, cache_components, temp_dir):
        """Test that cache keys use the correct prefix."""
        search_cache, _, _ = cache_components

        # Access the key generation method
        key = search_cache._make_key(
            operation="grep",
            pattern="TODO",
            scope=temp_dir,
            options={"case_sensitive": True}
        )

        assert key.startswith("_search:")
        assert len(key) == len("_search:") + 16  # prefix + 16-char hash

    async def test_resolved_paths_in_keys(self, cache_components, temp_dir):
        """Test that relative paths are resolved in cache keys."""
        search_cache, _, _ = cache_components

        # Create a subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()

        options = {"case_sensitive": True}

        # Cache using absolute path
        await search_cache.set_search_result(
            operation="grep",
            pattern="TODO",
            scope=subdir.resolve(),
            options=options,
            result="absolute path result"
        )

        # Retrieve using the subdirectory path
        result = await search_cache.get_search_result(
            operation="grep",
            pattern="TODO",
            scope=subdir,
            options=options
        )

        # Should get the same result because paths are resolved
        assert result == "absolute path result"
