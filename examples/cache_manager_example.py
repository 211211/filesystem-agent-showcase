"""
Example usage of the CacheManager unified cache interface.

This example demonstrates:
1. Initializing CacheManager with default settings
2. Using ContentCache to cache file content
3. Using SearchCache to cache search results
4. Getting cache statistics
5. Clearing all caches
"""

import asyncio
from pathlib import Path

from app.cache import CacheManager


async def main():
    """Demonstrate CacheManager usage."""
    print("=" * 60)
    print("CacheManager Example")
    print("=" * 60)

    # Initialize cache manager with default settings from environment
    print("\n1. Initializing CacheManager with default settings...")
    manager = CacheManager.default()
    print(f"   Cache directory: {manager.persistent_cache._cache.directory}")

    # Get initial statistics
    print("\n2. Initial cache statistics:")
    stats = manager.stats()
    print(f"   Entries: {stats['disk_cache']['size']}")
    print(f"   Disk usage: {stats['disk_cache']['volume']} bytes")
    print(f"   Content TTL: {stats['content_ttl']}s")
    print(f"   Search TTL: {stats['search_ttl']}s")

    # Example 1: Cache file content
    print("\n3. Caching file content...")
    test_file = Path("data/example.txt")

    if not test_file.exists():
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("Hello, World!\nThis is a test file.")
        print(f"   Created test file: {test_file}")

    async def load_file_content(path: Path) -> str:
        """Load file content (this would be called on cache miss)."""
        print(f"   Loading content from disk: {path}")
        return path.read_text()

    # First access - cache miss
    print(f"   First access (cache miss):")
    content1 = await manager.content_cache.get_content(test_file, load_file_content)
    print(f"   Content length: {len(content1)} characters")

    # Second access - cache hit
    print(f"   Second access (cache hit):")
    content2 = await manager.content_cache.get_content(test_file, load_file_content)
    print(f"   Content length: {len(content2)} characters")

    # Example 2: Cache search results
    print("\n4. Caching search results...")
    search_scope = Path("data")

    # Cache a search result
    await manager.search_cache.set_search_result(
        operation="grep",
        pattern="test",
        scope=test_file,  # Use file as scope
        options={"case_sensitive": True},
        result="example.txt:2:This is a test file.",
        ttl=300,  # 5 minutes
    )
    print(f"   Cached search result for pattern 'test' in {search_scope}")

    # Retrieve cached search result
    cached_result = await manager.search_cache.get_search_result(
        operation="grep",
        pattern="test",
        scope=test_file,
        options={"case_sensitive": True},
    )
    print(f"   Retrieved cached result: {cached_result}")

    # Get updated statistics
    print("\n5. Cache statistics after operations:")
    stats = manager.stats()
    print(f"   Entries: {stats['disk_cache']['size']}")
    print(f"   Disk usage: {stats['disk_cache']['volume']} bytes")

    # Example 3: File state tracking
    print("\n6. File state tracking...")
    is_stale = await manager.file_state_tracker.is_stale(test_file)
    print(f"   Is file stale? {is_stale}")

    # Modify the file
    test_file.write_text("Modified content")
    print(f"   Modified file: {test_file}")

    is_stale = await manager.file_state_tracker.is_stale(test_file)
    print(f"   Is file stale now? {is_stale}")

    # Example 4: Clear all caches
    print("\n7. Clearing all caches...")
    await manager.clear_all()
    stats = manager.stats()
    print(f"   Entries after clear: {stats['disk_cache']['size']}")

    # Clean up
    print("\n8. Closing cache manager...")
    manager.close()
    print("   Done!")

    print("\n" + "=" * 60)
    print("CacheManager example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
