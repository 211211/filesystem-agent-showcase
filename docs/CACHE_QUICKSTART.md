# Cache System Quick Start Guide

## TL;DR

Enable the new cache system in 3 lines:

```python
from app.agent.filesystem_agent import create_agent

agent = create_agent(
    # ... your normal parameters ...
    use_new_cache=True,  # 🔥 Enable new cache!
)
```

That's it! Your agent now has persistent, intelligent caching.

---

## What You Get

✅ **Persistent Cache** - Survives restarts
✅ **Auto File Detection** - Invalidates when files change
✅ **50-150x Faster** - For cache hits
✅ **Zero Breaking Changes** - Backward compatible

---

## Quick Examples

### Example 1: Basic Usage

```python
from pathlib import Path
from app.agent.filesystem_agent import create_agent

# Create agent with new cache
agent = create_agent(
    api_key="your_key",
    endpoint="https://your-endpoint.openai.azure.com",
    deployment_name="gpt-4",
    api_version="2024-02-15-preview",
    data_root=Path("./data"),
    use_new_cache=True,
)

# Use normally
response = await agent.chat("Find all Python files")
```

### Example 2: Custom Configuration

```python
agent = create_agent(
    # ... normal params ...
    use_new_cache=True,
    cache_directory="custom/cache",        # Default: "tmp/cache"
    cache_size_limit=1024 * 1024 * 1024,   # Default: 500MB
    cache_content_ttl=0,                   # Default: 0 (no expiry)
    cache_search_ttl=600,                  # Default: 300 (5 min)
)
```

### Example 3: Check Cache Stats

```python
stats = agent.get_cache_stats()
print(f"Cache size: {stats['new_cache']['disk_cache']['size']} entries")
print(f"Disk usage: {stats['new_cache']['disk_cache']['volume']} bytes")
```

### Example 4: Manual Cache Management

```python
# Invalidate specific file
await agent.cache_manager.invalidate_file(Path("data/config.json"))

# Clear all caches
await agent.cache_manager.clear_all()

# Invalidate directory
count = await agent.cache_manager.invalidate_directory(Path("data/logs/"))
```

---

## Configuration

### Via Environment Variables

Create/update `.env`:

```bash
# Enable new cache
USE_NEW_CACHE=true

# Configure cache
CACHE_DIRECTORY=tmp/cache
CACHE_SIZE_LIMIT=524288000  # 500MB
CACHE_CONTENT_TTL=0         # No expiry
CACHE_SEARCH_TTL=300        # 5 minutes
```

### Via Code

```python
from app.config import get_settings

settings = get_settings()
agent = create_agent(
    api_key=settings.azure_openai_api_key,
    endpoint=settings.azure_openai_endpoint,
    deployment_name=settings.azure_openai_deployment_name,
    api_version=settings.azure_openai_api_version,
    data_root=settings.data_root,
    use_new_cache=True,
    cache_directory=settings.cache_directory,
    cache_size_limit=settings.cache_size_limit,
)
```

---

## What Gets Cached?

### ✅ Cached Operations

- `cat` - Read entire file
- `head` - Read first N lines
- `grep` - Search for pattern
- `find` - Find files by name

### ❌ Not Cached

- `ls` - List directory (changes frequently)
- `wc` - Word count (fast operation)
- `tree` - Directory tree (changes frequently)

---

## How It Works

```
┌─────────────────────────────────────┐
│ First Access                        │
│ cat file.txt → Cache MISS           │
│                                     │
│ 1. Read from disk                   │
│ 2. Cache result                     │
│ 3. Return content                   │
│                                     │
│ Time: 250ms                         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Second Access                       │
│ cat file.txt → Cache HIT            │
│                                     │
│ 1. Check if file changed (no)       │
│ 2. Return cached content            │
│                                     │
│ Time: 5ms (50x faster!)             │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ After File Change                   │
│ cat file.txt → Cache MISS           │
│                                     │
│ 1. Detect file changed              │
│ 2. Invalidate cache                 │
│ 3. Read fresh from disk             │
│ 4. Cache new result                 │
│                                     │
│ Time: 250ms                         │
└─────────────────────────────────────┘
```

---

## Testing

### Run Cache Tests

```bash
# All cache integration tests
pytest tests/test_agent_cache_integration.py -v

# Specific test
pytest tests/test_agent_cache_integration.py::TestCacheIntegration::test_cached_cat_operation -v
```

### Run Demo

```bash
# Interactive demo
python examples/cache_demo.py
```

---

## Troubleshooting

### Problem: Cache not working

**Solution:**
```python
# Check if cache is enabled
stats = agent.get_cache_stats()
print(stats['new_cache'])

# Should show:
# {
#     'disk_cache': {'size': 0, 'volume': 0, 'directory': 'tmp/cache'},
#     'content_ttl': 0,
#     'search_ttl': 300,
#     ...
# }
```

### Problem: Cache directory permission error

**Solution:**
```python
# Use a writable directory
agent = create_agent(
    # ...
    cache_directory="/path/to/writable/dir",
)
```

### Problem: Cache growing too large

**Solution:**
```python
# Reduce size limit
agent = create_agent(
    # ...
    cache_size_limit=100 * 1024 * 1024,  # 100MB instead of 500MB
)

# Or clear cache periodically
await agent.cache_manager.clear_all()
```

### Problem: Stale data returned

**Solution:**
```python
# Manually invalidate
await agent.cache_manager.invalidate_file(Path("data/file.txt"))

# Or invalidate directory
await agent.cache_manager.invalidate_directory(Path("data/"))
```

---

## Migration from Old Cache

### Step 1: Test with new cache

```python
# Add flag to existing code
agent = create_agent(
    # ... existing params ...
    use_new_cache=True,  # Add this line
)
```

### Step 2: Compare performance

```python
import time

# Measure with old cache
agent_old = create_agent(..., cache_enabled=True)
start = time.time()
await agent_old.chat("Read large_file.txt")
time_old = time.time() - start

# Measure with new cache
agent_new = create_agent(..., use_new_cache=True)
start = time.time()
await agent_new.chat("Read large_file.txt")
time_new = time.time() - start

print(f"Old cache: {time_old:.3f}s")
print(f"New cache: {time_new:.3f}s")
```

### Step 3: Switch permanently

```python
# Update your code
agent = create_agent(
    # ...
    use_new_cache=True,
    cache_enabled=False,  # Disable old cache
)
```

---

## Best Practices

### ✅ DO

- Enable new cache for production workloads
- Monitor cache size and hit rates
- Use appropriate size limits for your use case
- Clear cache when handling sensitive data

### ❌ DON'T

- Don't set cache_content_ttl > 0 (rely on file state tracking)
- Don't use cache_size_limit too small (causes thrashing)
- Don't share cache directory between different data roots
- Don't forget to handle cache directory permissions

---

## Performance Tips

### For Small Projects (< 100 files)

```python
agent = create_agent(
    # ...
    use_new_cache=True,
    cache_size_limit=100 * 1024 * 1024,  # 100MB
)
```

### For Large Projects (> 1000 files)

```python
agent = create_agent(
    # ...
    use_new_cache=True,
    cache_size_limit=2 * 1024 * 1024 * 1024,  # 2GB
    cache_search_ttl=600,  # 10 minutes
)
```

### For Rapidly Changing Codebases

```python
agent = create_agent(
    # ...
    use_new_cache=True,
    cache_search_ttl=60,  # 1 minute (shorter TTL)
)
```

---

## Monitoring

### Log Cache Activity

```python
import logging

# Enable cache logging
logging.getLogger('app.agent.filesystem_agent').setLevel(logging.DEBUG)
logging.getLogger('app.cache').setLevel(logging.DEBUG)

# Now you'll see:
# DEBUG - Cache HIT: data/file.txt
# DEBUG - Cache MISS: data/other.txt
```

### Track Cache Metrics

```python
# Before operation
stats_before = agent.get_cache_stats()

# Perform operations
await agent.chat("Find all Python files")
await agent.chat("Read README.md")

# After operation
stats_after = agent.get_cache_stats()

# Calculate metrics
cache_growth = stats_after['new_cache']['disk_cache']['size'] - \
               stats_before['new_cache']['disk_cache']['size']
print(f"Cache entries added: {cache_growth}")
```

---

## API Reference

### Agent Methods

```python
# Get cache statistics
stats = agent.get_cache_stats()

# Returns:
# {
#     'new_cache': {
#         'disk_cache': {
#             'size': 10,
#             'volume': 1048576,
#             'directory': 'tmp/cache'
#         },
#         'content_ttl': 0,
#         'search_ttl': 300,
#         ...
#     },
#     'old_cache': {
#         'enabled': False
#     }
# }
```

### CacheManager Methods

```python
# Invalidate specific file
await agent.cache_manager.invalidate_file(Path("file.txt"))

# Invalidate directory
count = await agent.cache_manager.invalidate_directory(Path("dir/"))

# Clear all caches
await agent.cache_manager.clear_all()

# Get stats
stats = agent.cache_manager.stats()

# Close cache (cleanup)
agent.cache_manager.close()
```

---

## Getting Help

### Documentation

- [CACHE_INTEGRATION_GUIDE.md](CACHE_INTEGRATION_GUIDE.md) - Complete guide
- [CACHE_INTEGRATION_SUMMARY.md](CACHE_INTEGRATION_SUMMARY.md) - Implementation details
- [CACHE_IMPROVEMENT_PLAN_VI.md](CACHE_IMPROVEMENT_PLAN_VI.md) - Architecture design

### Code Examples

- [examples/cache_demo.py](../examples/cache_demo.py) - Interactive demos
- [tests/test_agent_cache_integration.py](../tests/test_agent_cache_integration.py) - Test examples

### Support

1. Check logs: `logging.getLogger('app.cache').setLevel(logging.DEBUG)`
2. Verify stats: `agent.get_cache_stats()`
3. Review documentation above
4. Check existing issues/tests

---

## What's Next?

After enabling the new cache:

1. **Monitor Performance**
   - Track cache hit rates
   - Measure response times
   - Monitor disk usage

2. **Tune Configuration**
   - Adjust cache_size_limit if needed
   - Modify cache_search_ttl for your use case
   - Change cache_directory if preferred

3. **Provide Feedback**
   - Report any issues
   - Share performance improvements
   - Suggest enhancements

Enjoy faster, smarter caching! 🚀
