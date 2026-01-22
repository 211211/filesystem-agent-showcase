# CacheManager - Unified Cache Interface

The `CacheManager` class provides a unified interface to all caching components in the filesystem-agent-showcase project. It orchestrates `PersistentCache`, `FileStateTracker`, `ContentCache`, and `SearchCache` into a cohesive caching system.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CacheManager                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ ContentCache │    │ SearchCache  │    │ FileState    │  │
│  │              │    │              │    │ Tracker      │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                   │                    │          │
│         └───────────────────┴────────────────────┘          │
│                             │                                │
│                    ┌────────▼─────────┐                      │
│                    │ PersistentCache  │                      │
│                    │   (DiskCache)    │                      │
│                    └──────────────────┘                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
from app.cache import CacheManager

# Initialize with default settings from environment variables
manager = CacheManager.default()

# Use the cache components
stats = manager.stats()
print(f"Cache entries: {stats['disk_cache']['size']}")

# Clean up when done
manager.close()
```

### Custom Configuration

```python
from app.cache import CacheManager

# Initialize with custom settings
manager = CacheManager(
    cache_dir="custom/cache",
    size_limit=1024 * 1024 * 1024,  # 1GB
    content_ttl=0,  # No expiry for content
    search_ttl=600,  # 10 minutes for search
)
```

## Environment Configuration

The `CacheManager` can be configured via environment variables:

```bash
# Cache directory path (default: tmp/cache)
CACHE_DIRECTORY=tmp/cache

# Maximum cache size in bytes (default: 524288000 = 500MB)
CACHE_SIZE_LIMIT=524288000

# Time-to-live for cached file content in seconds (default: 0 = no expiry)
# Set to 0 to invalidate on file changes only
CACHE_CONTENT_TTL=0

# Time-to-live for cached search results in seconds (default: 300 = 5 minutes)
CACHE_SEARCH_TTL=300
```

## Components

### 1. PersistentCache

Low-level disk-based cache backend using DiskCache with LRU eviction.

```python
# Access the persistent cache
await manager.persistent_cache.set("key", "value")
value = await manager.persistent_cache.get("key")
```

### 2. FileStateTracker

Tracks file states (mtime, size, content hash) for change detection.

```python
# Check if a file has changed
from pathlib import Path

file_path = Path("data/document.txt")
is_stale = await manager.file_state_tracker.is_stale(file_path)

if is_stale:
    # File has changed, invalidate related caches
    await manager.file_state_tracker.update_state(file_path)
```

### 3. ContentCache

Caches file content with automatic staleness detection.

```python
from pathlib import Path

# Define a loader function
async def load_content(path: Path) -> str:
    return path.read_text()

# Get content (from cache or load if stale)
content = await manager.content_cache.get_content(
    Path("data/document.txt"),
    load_content
)

# Invalidate specific file
await manager.content_cache.invalidate(Path("data/document.txt"))

# Invalidate entire directory
count = await manager.content_cache.invalidate_directory(Path("data/"))
```

### 4. SearchCache

Caches search results with scope-aware invalidation.

```python
from pathlib import Path

scope = Path("data/documents")
options = {"case_sensitive": True, "max_results": 100}

# Cache a search result
await manager.search_cache.set_search_result(
    operation="grep",
    pattern="TODO",
    scope=scope,
    options=options,
    result="file1.py:10:# TODO: fix this\nfile2.py:20:# TODO: test",
    ttl=300
)

# Retrieve cached result
result = await manager.search_cache.get_search_result(
    operation="grep",
    pattern="TODO",
    scope=scope,
    options=options
)
```

## API Reference

### Initialization

#### `CacheManager.__init__(cache_dir, size_limit, content_ttl, search_ttl)`

Initialize CacheManager with custom settings.

**Parameters:**
- `cache_dir` (str): Directory for cache storage. Default: "tmp/cache"
- `size_limit` (int): Maximum cache size in bytes. Default: 524,288,000 (500MB)
- `content_ttl` (float): TTL for content cache in seconds. Default: 0 (no expiry)
- `search_ttl` (float): TTL for search cache in seconds. Default: 300 (5 minutes)

#### `CacheManager.default(settings=None)`

Create CacheManager with default settings from environment variables.

**Parameters:**
- `settings` (Settings, optional): Settings instance. If None, loads from environment.

**Returns:**
- `CacheManager`: Configured cache manager instance

### Methods

#### `stats() -> dict`

Get comprehensive cache statistics.

**Returns:**
```python
{
    "disk_cache": {
        "size": 42,           # Number of entries
        "volume": 1024000,    # Disk usage in bytes
        "directory": "tmp/cache"
    },
    "content_ttl": 0,
    "search_ttl": 300,
    "configuration": {
        "cache_directory": "tmp/cache",
        "size_limit": 524288000,
        "eviction_policy": "least-recently-used"
    }
}
```

#### `async clear_all()`

Clear all caches and reset all tracking state.

**Warning:** This operation is irreversible and removes all cached data.

#### `close()`

Close the cache manager and release resources.

Should be called when the cache manager is no longer needed.

### Context Manager Usage

```python
async with CacheManager.default() as manager:
    # Use cache manager
    content = await manager.content_cache.get_content(
        Path("data.txt"),
        lambda p: p.read_text()
    )
    # Automatically cleaned up on exit
```

## Cache Behavior

### Content Cache

- **Invalidation:** Based on file state changes (mtime, size, content hash)
- **TTL:** Configurable, default is 0 (no time-based expiry)
- **Key Format:** `_content:<absolute_path>`
- **Use Case:** Cache file content that doesn't change frequently

### Search Cache

- **Invalidation:** Based on search scope changes
- **TTL:** Configurable, default is 300 seconds (5 minutes)
- **Key Format:** `_search:<hash_of_operation_params>`
- **Use Case:** Cache search results (grep, find) that depend on file state

### File State Tracking

- **Tracks:** Modification time, file size, content hash (for files < 1MB)
- **Key Format:** `_filestate:<absolute_path>`
- **Use Case:** Detect when files change to invalidate dependent caches

## Performance Considerations

1. **LRU Eviction:** When cache size exceeds the limit, least-recently-used entries are automatically evicted
2. **Content Hash:** Only computed for files < 1MB to balance accuracy and performance
3. **Directory Changes:** Detected via directory mtime (faster than checking all files)
4. **Async Operations:** All cache operations are async-safe with proper locking

## Best Practices

1. **Use `default()` for initialization** to load configuration from environment
2. **Always call `close()`** or use context manager for proper cleanup
3. **Monitor cache stats** to tune size limits and TTL values
4. **Use appropriate TTL values:**
   - Content cache: 0 (invalidate on change only)
   - Search cache: 300-600 seconds (balance freshness vs. performance)
5. **Clear caches selectively** instead of clearing everything when possible

## Example

See `examples/cache_manager_example.py` for a complete working example.

## Testing

Run the test suite:

```bash
poetry run pytest tests/test_cache_manager.py -v
```

## Related Documentation

- [CACHE_IMPROVEMENT_PLAN_VI.md](./CACHE_IMPROVEMENT_PLAN_VI.md) - Detailed cache architecture
- [disk_cache.py](../app/cache/disk_cache.py) - PersistentCache implementation
- [file_state.py](../app/cache/file_state.py) - FileStateTracker implementation
- [content_cache.py](../app/cache/content_cache.py) - ContentCache implementation
- [search_cache.py](../app/cache/search_cache.py) - SearchCache implementation
