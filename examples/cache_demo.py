"""
Demo script showing the new cache system integration with FilesystemAgent.

This script demonstrates:
1. Creating an agent with the new cache system
2. Performing cached operations
3. Retrieving cache statistics
4. File change detection
"""

import asyncio
import time
from pathlib import Path
from app.agent.filesystem_agent import create_agent
from app.config import get_settings


async def demo_basic_caching():
    """Demonstrate basic caching functionality."""
    print("=" * 60)
    print("Demo 1: Basic Caching")
    print("=" * 60)

    # Load settings
    settings = get_settings()

    # Create agent with new cache
    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,  # Enable new cache
        cache_directory="tmp/demo_cache",
        cache_size_limit=100 * 1024 * 1024,  # 100MB
    )

    # Create test file
    test_file = settings.data_root / "cache_demo.txt"
    test_file.write_text("Hello from cache demo!")

    print("\n1. First read (cache miss):")
    start = time.time()
    response1 = await agent.chat("Read the file cache_demo.txt")
    time1 = time.time() - start
    print(f"   Response: {response1.message[:100]}...")
    print(f"   Time: {time1:.3f}s")

    print("\n2. Second read (cache hit):")
    start = time.time()
    response2 = await agent.chat("Read the file cache_demo.txt")
    time2 = time.time() - start
    print(f"   Response: {response2.message[:100]}...")
    print(f"   Time: {time2:.3f}s")
    print(f"   Speedup: {time1/time2:.1f}x")

    # Get cache stats
    stats = agent.get_cache_stats()
    print("\n3. Cache Statistics:")
    print(f"   Entries: {stats['new_cache']['disk_cache']['size']}")
    print(f"   Disk usage: {stats['new_cache']['disk_cache']['volume']} bytes")

    # Cleanup
    test_file.unlink()


async def demo_file_change_detection():
    """Demonstrate automatic file change detection."""
    print("\n" + "=" * 60)
    print("Demo 2: File Change Detection")
    print("=" * 60)

    settings = get_settings()

    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,
        cache_directory="tmp/demo_cache",
    )

    test_file = settings.data_root / "changeable.txt"
    test_file.write_text("Version 1")

    print("\n1. Read initial version:")
    response1 = await agent.chat("Read changeable.txt")
    print(f"   Content: Version 1 found: {'Version 1' in response1.message}")

    print("\n2. Modify file:")
    test_file.write_text("Version 2")
    print("   File updated to 'Version 2'")

    print("\n3. Read again (should detect change):")
    response2 = await agent.chat("Read changeable.txt")
    print(f"   Content: Version 2 found: {'Version 2' in response2.message}")
    print(f"   Cache invalidated: {'Version 1' not in response2.message}")

    # Cleanup
    test_file.unlink()


async def demo_search_caching():
    """Demonstrate search result caching."""
    print("\n" + "=" * 60)
    print("Demo 3: Search Result Caching")
    print("=" * 60)

    settings = get_settings()

    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,
        cache_directory="tmp/demo_cache",
    )

    # Create test files
    (settings.data_root / "file1.py").write_text("# TODO: implement feature A")
    (settings.data_root / "file2.py").write_text("# TODO: implement feature B")

    print("\n1. First search (cache miss):")
    start = time.time()
    response1 = await agent.chat("Find all TODO comments in Python files")
    time1 = time.time() - start
    print(f"   Found TODOs: {'TODO' in response1.message}")
    print(f"   Time: {time1:.3f}s")

    print("\n2. Second search (cache hit):")
    start = time.time()
    response2 = await agent.chat("Find all TODO comments in Python files")
    time2 = time.time() - start
    print(f"   Found TODOs: {'TODO' in response2.message}")
    print(f"   Time: {time2:.3f}s")
    print(f"   Speedup: {time1/time2:.1f}x")

    # Cleanup
    (settings.data_root / "file1.py").unlink()
    (settings.data_root / "file2.py").unlink()


async def demo_cache_statistics():
    """Demonstrate cache statistics monitoring."""
    print("\n" + "=" * 60)
    print("Demo 4: Cache Statistics")
    print("=" * 60)

    settings = get_settings()

    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,
        cache_directory="tmp/demo_cache",
    )

    print("\n1. Initial stats:")
    stats = agent.get_cache_stats()
    print(f"   New cache enabled: {stats['new_cache'].get('enabled', True)}")
    print(f"   Old cache enabled: {stats['old_cache']['enabled']}")

    print("\n2. Cache configuration:")
    if stats['new_cache'].get('enabled', True):
        print(f"   Content TTL: {stats['new_cache']['content_ttl']}s")
        print(f"   Search TTL: {stats['new_cache']['search_ttl']}s")
        print(f"   Directory: {stats['new_cache']['disk_cache']['directory']}")

    print("\n3. Perform some operations...")
    test_file = settings.data_root / "stats_demo.txt"
    test_file.write_text("Sample content")
    await agent.chat("Read stats_demo.txt")
    await agent.chat("Find all txt files")

    print("\n4. Updated stats:")
    stats = agent.get_cache_stats()
    print(f"   Cache entries: {stats['new_cache']['disk_cache']['size']}")
    print(f"   Disk usage: {stats['new_cache']['disk_cache']['volume']} bytes")

    # Cleanup
    test_file.unlink()


async def demo_manual_cache_management():
    """Demonstrate manual cache management."""
    print("\n" + "=" * 60)
    print("Demo 5: Manual Cache Management")
    print("=" * 60)

    settings = get_settings()

    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,
        cache_directory="tmp/demo_cache",
    )

    # Create and cache some files
    test_file = settings.data_root / "managed.txt"
    test_file.write_text("Managed content")
    await agent.chat("Read managed.txt")

    print("\n1. Cache populated:")
    stats = agent.get_cache_stats()
    print(f"   Entries: {stats['new_cache']['disk_cache']['size']}")

    print("\n2. Manually invalidate file:")
    await agent.cache_manager.invalidate_file(test_file)
    print("   File cache invalidated")

    print("\n3. Clear all caches:")
    await agent.cache_manager.clear_all()
    stats = agent.get_cache_stats()
    print(f"   Entries after clear: {stats['new_cache']['disk_cache']['size']}")

    # Cleanup
    test_file.unlink()


async def main():
    """Run all demos."""
    print("\n" + "🚀 " * 20)
    print("Cache System Integration Demo")
    print("🚀 " * 20)

    try:
        await demo_basic_caching()
        await demo_file_change_detection()
        await demo_search_caching()
        await demo_cache_statistics()
        await demo_manual_cache_management()

        print("\n" + "✅ " * 20)
        print("All demos completed successfully!")
        print("✅ " * 20)

    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        import shutil
        cache_dir = Path("tmp/demo_cache")
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            print("\n🧹 Cleaned up demo cache directory")


if __name__ == "__main__":
    asyncio.run(main())
