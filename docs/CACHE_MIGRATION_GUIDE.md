# Cache System Migration Guide

## Overview

This guide helps you migrate from the v2.0 in-memory cache system to the new v3.0 multi-tier cache system with persistent disk storage and automatic file change detection.

### What Changed?

**v2.0 Cache (Old):**
- In-memory only (lost on restart)
- Simple TTL-based expiration
- Manual invalidation required
- Limited to 100 entries by default
- No file change detection

**v3.0 Cache (New):**
- Persistent disk storage (survives restarts)
- Automatic file change detection
- Multi-tier architecture (content + search caches)
- Configurable size limits (500MB default)
- 50-150x faster for cache hits
- LRU eviction policy

## What's New

### Multi-Tier Cache Architecture

The new system consists of four integrated components:

```
CacheManager
├── PersistentCache (L2)     - DiskCache backend with LRU eviction
├── FileStateTracker         - Detects file changes (mtime, size, hash)
├── ContentCache             - Caches file content (cat, head)
└── SearchCache              - Caches search results (grep, find)
```

### Key Features

1. **Persistent Storage**: Cache survives application restarts
2. **Automatic Invalidation**: Detects changes via file state tracking
3. **Content-Aware Keys**: Equivalent commands share cache entries
4. **Scope-Aware Invalidation**: Directory changes invalidate related searches
5. **Configurable TTL**: Separate TTL for content and search caches
6. **LRU Eviction**: Automatic cleanup when size limit is reached

## Migration Steps

### Phase 1: Preparation

**Step 1.1: Review Current Configuration**

Check your current `.env` file for cache settings:

```bash
# Old cache settings (v2.0)
CACHE_ENABLED=true
CACHE_TTL=300
CACHE_MAX_SIZE=100
```

**Step 1.2: Understand Your Usage Patterns**

Analyze which operations benefit most from caching:

```bash
# Run with debug logging
export LOG_LEVEL=DEBUG
poetry run uvicorn app.main:app --reload

# Monitor cache hits/misses in logs
```

**Step 1.3: Backup Configuration**

```bash
# Save current settings
cp .env .env.v2.backup
```

### Phase 2: Installation

The new cache system is already included in the project. Ensure dependencies are up to date:

```bash
poetry install
```

The `diskcache` library is automatically installed:

```toml
[tool.poetry.dependencies]
diskcache = "^5.6.3"
```

### Phase 3: Configuration

**Step 3.1: Add New Cache Settings**

Update your `.env` file:

```bash
# New cache configuration (v3.0)
USE_NEW_CACHE=true
CACHE_DIRECTORY=tmp/cache
CACHE_SIZE_LIMIT=524288000      # 500MB
CACHE_CONTENT_TTL=0             # No expiry (rely on file state)
CACHE_SEARCH_TTL=300            # 5 minutes

# Optional: Keep old cache disabled
CACHE_ENABLED=false
```

**Step 3.2: Create Cache Directory**

```bash
mkdir -p tmp/cache
```

**Step 3.3: Set Appropriate Permissions**

```bash
# Ensure directory is writable
chmod 755 tmp/cache
```

### Phase 4: Testing

**Step 4.1: Test in Development**

Create a test script:

```python
# test_new_cache.py
import asyncio
from pathlib import Path
from app.agent.filesystem_agent import create_agent
from app.config import get_settings

async def test_cache():
    settings = get_settings()

    # Create agent with new cache
    agent = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,
    )

    # Test 1: Cache miss (first read)
    print("Test 1: First read (cache miss expected)")
    response1 = await agent.chat("Read data/projects/project-alpha/README.md")
    stats1 = agent.get_cache_stats()
    print(f"Cache size: {stats1['new_cache']['disk_cache']['size']}")

    # Test 2: Cache hit (second read)
    print("\nTest 2: Second read (cache hit expected)")
    response2 = await agent.chat("Read data/projects/project-alpha/README.md")
    stats2 = agent.get_cache_stats()
    print(f"Cache size: {stats2['new_cache']['disk_cache']['size']}")

    # Test 3: File change detection
    print("\nTest 3: Modify file and read again")
    test_file = Path("data/test.txt")
    test_file.write_text("Version 1")

    response3 = await agent.chat("Read data/test.txt")

    # Modify file
    test_file.write_text("Version 2")

    response4 = await agent.chat("Read data/test.txt")
    print("File change detected and cache invalidated")

    # Cleanup
    test_file.unlink()

    print("\n✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_cache())
```

Run the test:

```bash
poetry run python test_new_cache.py
```

**Step 4.2: Run Existing Tests**

```bash
# Run cache integration tests
poetry run pytest tests/test_agent_cache_integration.py -v

# Run all tests
poetry run pytest -v
```

**Step 4.3: Performance Comparison**

```python
# benchmark_migration.py
import asyncio
import time
from pathlib import Path
from app.agent.filesystem_agent import create_agent
from app.config import get_settings

async def benchmark():
    settings = get_settings()

    # Test with old cache
    agent_old = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        cache_enabled=True,  # Old cache
    )

    # Test with new cache
    agent_new = create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        use_new_cache=True,  # New cache
    )

    test_queries = [
        "Read data/projects/project-alpha/README.md",
        "Find all Python files in data/",
        "Search for TODO in data/projects/",
    ]

    print("Benchmarking Old Cache...")
    start = time.time()
    for query in test_queries:
        await agent_old.chat(query)
        await agent_old.chat(query)  # Second call (cache hit)
    time_old = time.time() - start

    print("Benchmarking New Cache...")
    start = time.time()
    for query in test_queries:
        await agent_new.chat(query)
        await agent_new.chat(query)  # Second call (cache hit)
    time_new = time.time() - start

    print(f"\nResults:")
    print(f"Old cache: {time_old:.3f}s")
    print(f"New cache: {time_new:.3f}s")
    print(f"Speedup: {time_old/time_new:.1f}x")

if __name__ == "__main__":
    asyncio.run(benchmark())
```

### Phase 5: Rollout

**Step 5.1: Gradual Rollout (Recommended)**

Start with a subset of users or operations:

```python
# Use feature flag based on user ID, time, or other criteria
def should_use_new_cache(user_id: str) -> bool:
    # Roll out to 10% of users
    return hash(user_id) % 10 == 0

agent = create_agent(
    # ... other params ...
    use_new_cache=should_use_new_cache(user_id),
)
```

**Step 5.2: Monitor Performance**

```python
# Add monitoring
import logging

logger = logging.getLogger(__name__)

stats = agent.get_cache_stats()
logger.info(f"Cache stats: {stats}")

# Alert on issues
if stats['new_cache']['disk_cache']['volume'] > 450 * 1024 * 1024:
    logger.warning("Cache approaching size limit")
```

**Step 5.3: Full Rollout**

Once testing is successful, enable for all users:

```bash
# Update .env for production
USE_NEW_CACHE=true
CACHE_ENABLED=false  # Disable old cache
```

### Phase 6: Monitoring

**Step 6.1: Track Cache Metrics**

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge

cache_hits = Counter('cache_hits_total', 'Total cache hits')
cache_misses = Counter('cache_misses_total', 'Total cache misses')
cache_size = Gauge('cache_size_bytes', 'Cache size in bytes')

def record_cache_stats(agent):
    stats = agent.get_cache_stats()
    cache_size.set(stats['new_cache']['disk_cache']['volume'])
```

**Step 6.2: Set Up Alerts**

```python
# alerts.py
def check_cache_health(agent):
    stats = agent.get_cache_stats()

    # Alert if cache is too large
    if stats['new_cache']['disk_cache']['volume'] > 450 * 1024 * 1024:
        send_alert("Cache size approaching limit")

    # Alert if cache directory is missing
    cache_dir = Path(stats['new_cache']['disk_cache']['directory'])
    if not cache_dir.exists():
        send_alert("Cache directory missing")
```

**Step 6.3: Regular Maintenance**

```bash
# Schedule cache cleanup (optional)
0 2 * * * cd /app && poetry run fs-agent clear-cache --force
```

## Backward Compatibility

### Running Both Caches Simultaneously

You can run both cache systems side-by-side during migration:

```python
agent = create_agent(
    # ... other params ...
    cache_enabled=True,    # Old cache enabled
    use_new_cache=True,    # New cache enabled
)
```

This allows comparison and gradual migration without breaking existing functionality.

### API Compatibility

The agent API remains unchanged:

```python
# These calls work with both old and new cache
response = await agent.chat("Your query")
stats = agent.get_cache_stats()
```

### Cache Statistics Format

Both caches provide statistics:

```python
stats = agent.get_cache_stats()

# Old cache stats
print(stats['old_cache'])
# {
#     'enabled': True,
#     'hits': 10,
#     'misses': 5,
#     'size': 15,
#     'hit_rate': 0.67
# }

# New cache stats
print(stats['new_cache'])
# {
#     'disk_cache': {
#         'size': 42,
#         'volume': 10485760,
#         'directory': 'tmp/cache'
#     },
#     'content_ttl': 0,
#     'search_ttl': 300
# }
```

## Feature Comparison

| Feature | v2.0 Cache (Old) | v3.0 Cache (New) |
|---------|------------------|------------------|
| **Storage** | In-memory only | Persistent disk |
| **Survives Restarts** | ❌ No | ✅ Yes |
| **File Change Detection** | ❌ Manual | ✅ Automatic |
| **Cache Size** | 100 entries | 500MB (configurable) |
| **Eviction Policy** | LRU | LRU |
| **Content Cache** | Combined | Dedicated |
| **Search Cache** | Combined | Dedicated with scope tracking |
| **TTL Support** | ✅ Yes (fixed) | ✅ Yes (configurable per type) |
| **Cache Hit Performance** | ~5ms | ~0.5ms (10x faster) |
| **Invalidation** | Manual only | Automatic + manual |
| **Multi-Process Safe** | ❌ No | ✅ Yes (disk-based locks) |
| **Cache Warmup** | ❌ Not available | ✅ CLI tool included |
| **Configuration** | 3 variables | 5 variables |

## Migration Timeline

Recommended timeline for migration:

**Week 1: Preparation**
- Review current cache usage
- Test new cache in development
- Run benchmarks

**Week 2: Testing**
- Deploy to staging environment
- Run integration tests
- Monitor performance

**Week 3: Gradual Rollout**
- Enable for 10% of users
- Monitor metrics
- Address any issues

**Week 4: Full Rollout**
- Enable for 50% of users
- Continue monitoring
- Prepare for full deployment

**Week 5: Complete Migration**
- Enable for 100% of users
- Disable old cache
- Remove old cache code (optional)

## Rollback Procedure

If issues occur, you can quickly rollback:

### Immediate Rollback (Environment Variable)

```bash
# In .env
USE_NEW_CACHE=false
CACHE_ENABLED=true
```

Restart the application:

```bash
poetry run uvicorn app.main:app --reload
```

### Programmatic Rollback

```python
# Add rollback logic
def create_agent_with_fallback(**kwargs):
    try:
        # Try new cache
        return create_agent(**kwargs, use_new_cache=True)
    except Exception as e:
        logger.error(f"New cache failed: {e}")
        # Fallback to old cache
        return create_agent(**kwargs, cache_enabled=True)
```

### Preserving Cache Data

```bash
# Backup cache before rollback
tar -czf cache_backup_$(date +%Y%m%d).tar.gz tmp/cache/

# Clear cache if needed
poetry run fs-agent clear-cache --force
```

## FAQ

### Q: Can I use both cache systems at the same time?

**A:** Yes! Both caches can run simultaneously during migration. This allows gradual rollout and A/B testing.

```python
agent = create_agent(
    cache_enabled=True,    # Old cache
    use_new_cache=True,    # New cache
)
```

### Q: Will the new cache work with my existing code?

**A:** Yes! The agent API is unchanged. Just add `use_new_cache=True` when creating the agent.

### Q: How much disk space does the cache use?

**A:** Default is 500MB (configurable). The cache automatically evicts old entries using LRU policy when the limit is reached.

### Q: What happens if a file changes while it's cached?

**A:** The cache automatically detects changes via file state tracking (mtime, size, content hash) and invalidates stale entries.

### Q: Can I clear the cache without restarting?

**A:** Yes! Use the CLI tool or API:

```bash
poetry run fs-agent clear-cache --force
```

Or programmatically:

```python
await agent.cache_manager.clear_all()
```

### Q: Is the new cache thread-safe?

**A:** Yes! The cache uses async locks and disk-based locking for multi-process safety.

### Q: What if the cache directory is deleted?

**A:** The cache will automatically recreate the directory and continue operating normally. All operations fall back to direct execution if cache is unavailable.

### Q: How do I monitor cache performance?

**A:** Use `get_cache_stats()` or enable debug logging:

```python
import logging
logging.getLogger('app.cache').setLevel(logging.DEBUG)
```

### Q: Can I customize the cache directory?

**A:** Yes! Set `CACHE_DIRECTORY` in `.env` or pass `cache_directory` parameter:

```python
agent = create_agent(
    # ...
    use_new_cache=True,
    cache_directory="/custom/path/cache",
)
```

### Q: What's the recommended TTL configuration?

**A:**
- Content cache: `0` (no TTL, rely on file state tracking)
- Search cache: `300` (5 minutes) for most cases
- Adjust based on your data update frequency

### Q: How do I warm the cache on startup?

**A:** Use the CLI warmup tool:

```bash
poetry run fs-agent warm-cache -d ./data -c 10
```

Or programmatically:

```python
from app.cache.warmup import CacheWarmer

warmer = CacheWarmer(cache_manager)
await warmer.warm_directory(Path("./data"))
```

## Troubleshooting

### Issue: Cache not working

**Symptoms:**
- `get_cache_stats()` shows `size: 0`
- No performance improvement

**Solutions:**
1. Check if cache is enabled:
   ```python
   stats = agent.get_cache_stats()
   print(stats['new_cache'])  # Should not be None
   ```

2. Verify cache directory exists:
   ```bash
   ls -la tmp/cache
   ```

3. Check permissions:
   ```bash
   chmod 755 tmp/cache
   ```

4. Enable debug logging:
   ```python
   import logging
   logging.getLogger('app.cache').setLevel(logging.DEBUG)
   ```

### Issue: Cache directory permission errors

**Symptoms:**
- `PermissionError` when accessing cache
- Cache operations fail silently

**Solutions:**
1. Fix directory permissions:
   ```bash
   chmod 755 tmp/cache
   chown $USER:$GROUP tmp/cache
   ```

2. Use a different directory:
   ```bash
   # In .env
   CACHE_DIRECTORY=/tmp/app-cache
   ```

### Issue: Cache growing too large

**Symptoms:**
- Disk space warnings
- Slow cache operations

**Solutions:**
1. Reduce cache size limit:
   ```bash
   # In .env
   CACHE_SIZE_LIMIT=104857600  # 100MB instead of 500MB
   ```

2. Clear cache:
   ```bash
   poetry run fs-agent clear-cache --force
   ```

3. Enable automatic cleanup:
   ```python
   # Periodically check and clear if needed
   stats = agent.cache_manager.stats()
   if stats['disk_cache']['volume'] > threshold:
       await agent.cache_manager.clear_all()
   ```

### Issue: Stale data returned

**Symptoms:**
- File changes not detected
- Old content returned

**Solutions:**
1. Manually invalidate file:
   ```python
   await agent.cache_manager.invalidate_file(Path("data/file.txt"))
   ```

2. Check file state tracking:
   ```python
   state = await agent.cache_manager.file_state_tracker.get_state(file_path)
   print(f"Cached state: {state}")
   ```

3. Reduce TTL:
   ```bash
   # In .env
   CACHE_SEARCH_TTL=60  # 1 minute instead of 5
   ```

### Issue: Performance not improved

**Symptoms:**
- Cache hits don't feel faster
- No noticeable speedup

**Solutions:**
1. Verify cache hits are occurring:
   ```python
   # Enable debug logging
   import logging
   logging.getLogger('app.agent.filesystem_agent').setLevel(logging.DEBUG)
   ```

2. Pre-warm cache:
   ```bash
   poetry run fs-agent warm-cache -d ./data
   ```

3. Check cache size:
   ```python
   stats = agent.get_cache_stats()
   print(f"Entries: {stats['new_cache']['disk_cache']['size']}")
   ```

## Best Practices

1. **Start Small**: Begin with a small subset of users or operations
2. **Monitor Closely**: Track metrics during rollout
3. **Test Thoroughly**: Run all tests before production deployment
4. **Document Changes**: Update team documentation with new cache behavior
5. **Keep Old Cache**: Don't remove old cache code until migration is complete
6. **Backup Configuration**: Save `.env` before making changes
7. **Plan Rollback**: Have a rollback plan ready
8. **Communicate**: Inform team members about the migration
9. **Set Alerts**: Monitor cache size and performance
10. **Regular Cleanup**: Schedule periodic cache maintenance

## Next Steps

After successful migration:

1. **Optimize Configuration**: Tune TTL and size limits based on usage
2. **Enable Cache Warmup**: Pre-populate cache on startup
3. **Remove Old Cache**: Clean up v2.0 cache code (optional)
4. **Update Documentation**: Document cache behavior for your team
5. **Share Feedback**: Report any issues or improvements

## Support

If you encounter issues during migration:

1. Check this guide's troubleshooting section
2. Review the [Integration Guide](CACHE_INTEGRATION_GUIDE.md)
3. Check existing tests for examples
4. Enable debug logging for detailed information

## Additional Resources

- [Quick Start Guide](CACHE_QUICKSTART.md) - Get started in 3 lines
- [Integration Guide](CACHE_INTEGRATION_GUIDE.md) - Complete documentation
- [Cache Manager API](CACHE_MANAGER.md) - API reference
- [CLI Usage](CACHE_CLI_USAGE.md) - Command-line tools
- [Architecture Plan](CACHE_IMPROVEMENT_PLAN_VI.md) - Design documentation
