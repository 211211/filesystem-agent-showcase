"""
Example demonstrating programmatic cache warmup usage.

This script shows how to use the cache warmup utilities directly
in your Python code without using the CLI.
"""

import asyncio
import logging
from pathlib import Path

from app.cache import CacheManager, warm_cache, warm_cache_selective

# Configure logging to see progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_warmup():
    """
    Example 1: Basic cache warmup for a directory.
    """
    print("\n" + "=" * 60)
    print("Example 1: Basic Cache Warmup")
    print("=" * 60)

    # Initialize cache manager with default settings
    cache_manager = CacheManager.default()

    # Warm cache for the data directory
    data_dir = Path("./data")
    if not data_dir.exists():
        print(f"Directory {data_dir} does not exist, skipping example")
        cache_manager.close()
        return

    print(f"\nWarming cache for directory: {data_dir}")

    stats = await warm_cache(
        cache_manager.content_cache,
        directory=data_dir,
        recursive=True,
        pattern="*",
        concurrency=10
    )

    # Display results
    print(f"\n{stats}")

    # Show cache statistics
    cache_stats = cache_manager.stats()
    print(f"\nTotal cache entries: {cache_stats['disk_cache']['size']}")
    print(f"Total disk usage: {cache_stats['disk_cache']['volume'] / (1024 * 1024):.2f} MB")

    cache_manager.close()


async def example_selective_warmup():
    """
    Example 2: Selective cache warmup for specific files.
    """
    print("\n" + "=" * 60)
    print("Example 2: Selective Cache Warmup")
    print("=" * 60)

    # Initialize cache manager
    cache_manager = CacheManager.default()

    # List of important files to pre-cache
    important_files = [
        Path("./app/config.py"),
        Path("./app/main.py"),
        Path("./README.md"),
        Path("./pyproject.toml"),
    ]

    # Filter to only existing files
    existing_files = [f for f in important_files if f.exists()]

    if not existing_files:
        print("No example files found, skipping example")
        cache_manager.close()
        return

    print(f"\nCaching {len(existing_files)} specific files:")
    for file_path in existing_files:
        print(f"  - {file_path}")

    stats = await warm_cache_selective(
        cache_manager.content_cache,
        file_paths=existing_files,
        concurrency=5
    )

    print(f"\n{stats}")

    cache_manager.close()


async def example_pattern_based_warmup():
    """
    Example 3: Cache warmup with specific file patterns.
    """
    print("\n" + "=" * 60)
    print("Example 3: Pattern-Based Cache Warmup")
    print("=" * 60)

    cache_manager = CacheManager.default()

    # Warm cache for Python files only
    app_dir = Path("./app")
    if not app_dir.exists():
        print(f"Directory {app_dir} does not exist, skipping example")
        cache_manager.close()
        return

    print(f"\nCaching only Python files in: {app_dir}")

    stats = await warm_cache(
        cache_manager.content_cache,
        directory=app_dir,
        recursive=True,
        pattern="*.py",
        concurrency=10
    )

    print(f"\n{stats}")

    # Verify specific file is cached
    test_file = app_dir / "config.py"
    if test_file.exists():
        content = await cache_manager.content_cache.get_content(
            test_file,
            loader=lambda p: asyncio.to_thread(p.read_text, encoding='utf-8')
        )
        print(f"\nVerifying cache: {test_file.name} is cached ({len(content)} bytes)")

    cache_manager.close()


async def example_with_progress_callback():
    """
    Example 4: Cache warmup with custom progress callback.
    """
    print("\n" + "=" * 60)
    print("Example 4: Cache Warmup with Progress Tracking")
    print("=" * 60)

    cache_manager = CacheManager.default()

    app_dir = Path("./app")
    if not app_dir.exists():
        print(f"Directory {app_dir} does not exist, skipping example")
        cache_manager.close()
        return

    # Custom progress callback
    def progress_callback(current: int, total: int, file_path: Path):
        """Display progress bar."""
        percentage = (current / total) * 100
        bar_length = 40
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\r[{bar}] {percentage:.1f}% ({current}/{total}) - {file_path.name[:30]:<30}", end='', flush=True)

    print(f"\nWarming cache with progress bar: {app_dir}")

    stats = await warm_cache(
        cache_manager.content_cache,
        directory=app_dir,
        recursive=True,
        pattern="*.py",
        concurrency=10,
        progress_callback=progress_callback
    )

    print(f"\n\n{stats}")

    cache_manager.close()


async def example_cache_management():
    """
    Example 5: Complete cache management workflow.
    """
    print("\n" + "=" * 60)
    print("Example 5: Complete Cache Management Workflow")
    print("=" * 60)

    # Initialize cache manager
    cache_manager = CacheManager(
        cache_dir="tmp/example_cache",
        size_limit=100 * 1024 * 1024,  # 100MB
        content_ttl=0,
        search_ttl=300
    )

    print("\n1. Initial cache statistics:")
    stats = cache_manager.stats()
    print(f"   Entries: {stats['disk_cache']['size']}")
    print(f"   Size: {stats['disk_cache']['volume'] / (1024 * 1024):.2f} MB")

    # Warm cache
    app_dir = Path("./app")
    if app_dir.exists():
        print(f"\n2. Warming cache for {app_dir}")
        warmup_stats = await warm_cache(
            cache_manager.content_cache,
            directory=app_dir,
            recursive=True,
            pattern="*.py",
            concurrency=10
        )
        print(f"   Cached: {warmup_stats.files_succeeded} files")
        print(f"   Size: {warmup_stats.bytes_cached / (1024 * 1024):.2f} MB")

    print("\n3. Cache statistics after warmup:")
    stats = cache_manager.stats()
    print(f"   Entries: {stats['disk_cache']['size']}")
    print(f"   Size: {stats['disk_cache']['volume'] / (1024 * 1024):.2f} MB")

    print("\n4. Clearing cache...")
    await cache_manager.clear_all()

    print("\n5. Cache statistics after clearing:")
    stats = cache_manager.stats()
    print(f"   Entries: {stats['disk_cache']['size']}")
    print(f"   Size: {stats['disk_cache']['volume'] / (1024 * 1024):.2f} MB")

    cache_manager.close()


async def main():
    """
    Run all examples.
    """
    print("\n" + "=" * 60)
    print("Cache Warmup Examples")
    print("=" * 60)
    print("\nThese examples demonstrate different ways to use the")
    print("cache warmup utilities in your Python code.")

    try:
        # Run all examples
        await example_basic_warmup()
        await example_selective_warmup()
        await example_pattern_based_warmup()
        await example_with_progress_callback()
        await example_cache_management()

        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)

    except Exception as e:
        logger.exception(f"Error running examples: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
