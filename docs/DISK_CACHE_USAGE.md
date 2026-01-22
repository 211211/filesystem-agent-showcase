# PersistentCache Usage Guide

## Overview

The `PersistentCache` class provides a thread-safe, async-compatible wrapper around DiskCache for persistent caching with automatic LRU (Least Recently Used) eviction.

## Features

- **Persistent Storage**: Cache survives application restarts
- **Async/Await Interface**: Fully compatible with async Python code
- **Thread-Safe**: Uses `asyncio.Lock` for safe concurrent operations
- **Automatic Eviction**: LRU policy when size limit is reached
- **Size-Limited**: Configurable maximum cache size (default: 500MB)
- **TTL Support**: Optional expiration time for cached entries
- **Statistics**: Built-in metrics for monitoring cache performance

## Installation

The required dependency `diskcache` is already included in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
diskcache = "^5.6.3"
```

## Basic Usage

### Creating a Cache Instance

```python
from app.cache import PersistentCache

# Default settings (tmp/cache directory, 500MB limit)
cache = PersistentCache()

# Custom settings
cache = PersistentCache(
    cache_dir="custom/cache/path",
    size_limit=1024 * 1024 * 1024  # 1GB
)
```

### Storing and Retrieving Values

```python
# Store a value
await cache.set("user:123", {"name": "John", "email": "john@example.com"})

# Retrieve a value
user = await cache.get("user:123")
if user is None:
    print("Cache miss")
else:
    print(f"Cache hit: {user}")
```

### Using TTL (Time To Live)

```python
# Cache for 5 minutes
await cache.set("temp_data", "value", expire=300)

# Cache for 1 hour
await cache.set("session:abc", session_data, expire=3600)
```

### Deleting Entries

```python
# Delete a specific key
deleted = await cache.delete("user:123")
if deleted:
    print("Key was deleted")
else:
    print("Key not found")

# Clear all entries
await cache.clear()
```

### Cache Statistics

```python
stats = cache.stats()
print(f"Entries: {stats['size']}")
print(f"Size: {stats['volume'] / 1024 / 1024:.2f} MB")
print(f"Location: {stats['directory']}")
```

## Advanced Usage

### Using as Context Manager

```python
async with PersistentCache() as cache:
    await cache.set("key", "value")
    value = await cache.get("key")
    # Cache is automatically cleaned up on exit
```

### Concurrent Operations

The cache is thread-safe and can handle concurrent operations:

```python
import asyncio

async def cache_user(user_id: int, user_data: dict):
    await cache.set(f"user:{user_id}", user_data)

# Run multiple cache operations concurrently
await asyncio.gather(
    cache_user(1, {"name": "Alice"}),
    cache_user(2, {"name": "Bob"}),
    cache_user(3, {"name": "Charlie"}),
)
```

### Caching Complex Data

```python
# Dictionaries
await cache.set("config", {
    "api_url": "https://api.example.com",
    "timeout": 30,
    "retries": 3
})

# Lists
await cache.set("user_ids", [1, 2, 3, 4, 5])

# Nested structures
await cache.set("nested", {
    "users": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    ],
    "metadata": {
        "count": 2,
        "page": 1
    }
})
```

## Integration Example

### Caching File Content

```python
from pathlib import Path
from app.cache import PersistentCache

async def read_file_cached(file_path: Path, cache: PersistentCache) -> str:
    """Read file content with caching."""
    cache_key = f"file_content:{file_path.resolve()}"

    # Try to get from cache
    content = await cache.get(cache_key)
    if content is not None:
        return content

    # Cache miss - read from disk
    content = file_path.read_text()

    # Store in cache
    await cache.set(cache_key, content)

    return content
```

### Caching API Results

```python
import httpx

async def fetch_data_cached(url: str, cache: PersistentCache) -> dict:
    """Fetch data from API with caching."""
    cache_key = f"api_response:{url}"

    # Try cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    # Cache miss - fetch from API
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()

    # Cache for 5 minutes
    await cache.set(cache_key, data, expire=300)

    return data
```

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Cache Configuration
CACHE_DIRECTORY=tmp/cache
CACHE_SIZE_LIMIT=524288000      # 500MB
CACHE_CONTENT_TTL=0             # 0 = no expiry
CACHE_SEARCH_TTL=300            # 5 minutes
```

### Using with Settings

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    cache_directory: str = "tmp/cache"
    cache_size_limit: int = 500 * 1024 * 1024  # 500MB

    class Config:
        env_file = ".env"

settings = Settings()
cache = PersistentCache(
    cache_dir=settings.cache_directory,
    size_limit=settings.cache_size_limit
)
```

## Best Practices

1. **Choose Appropriate TTL**: Set expiration times based on data volatility
2. **Use Descriptive Keys**: Include prefixes like `"user:"`, `"file:"`, `"api:"`
3. **Monitor Cache Size**: Check `stats()` regularly to ensure cache is effective
4. **Handle Cache Misses**: Always check if `get()` returns `None`
5. **Close When Done**: Call `close()` or use context manager for proper cleanup
6. **Serialize Complex Objects**: Ensure cached data is pickle-able

## Performance Considerations

- **Cache Directory**: Use SSD storage for better performance
- **Size Limit**: Balance between hit rate and disk usage
- **LRU Eviction**: Most recently used items stay cached longer
- **Async Lock**: Protects against race conditions but adds slight overhead

## Troubleshooting

### Cache Not Persisting

```python
# Ensure you're using the same cache directory
cache1 = PersistentCache(cache_dir="tmp/cache")
cache2 = PersistentCache(cache_dir="tmp/cache")  # Same directory
```

### High Memory Usage

```python
# Reduce cache size limit
cache = PersistentCache(size_limit=100 * 1024 * 1024)  # 100MB
```

### Stale Data

```python
# Use TTL to auto-expire data
await cache.set("key", "value", expire=60)  # Expires after 1 minute
```

## Testing

Run the test suite to verify the implementation:

```bash
poetry run pytest tests/test_disk_cache.py -v
```

## See Also

- [DiskCache Documentation](https://grantjenks.com/docs/diskcache/)
- [Cache Improvement Plan](./CACHE_IMPROVEMENT_PLAN_VI.md)
- [File State Tracking](./file_state.py) (for cache invalidation)
