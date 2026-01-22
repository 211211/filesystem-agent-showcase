# Cache System Integration Guide

## Overview

This document describes the integration of the new CacheManager system into FilesystemAgent. The new cache system provides persistent, intelligent caching with automatic file change detection and scope-aware invalidation.

## Architecture

### Components

```
FilesystemAgent
├── cache_manager (Optional[CacheManager])
│   ├── persistent_cache (PersistentCache) - L2 disk cache
│   ├── file_state_tracker (FileStateTracker) - Detects file changes
│   ├── content_cache (ContentCache) - Caches file content
│   └── search_cache (SearchCache) - Caches search results
└── sandbox (SandboxExecutor) - Executes commands
```

### Cache Flow

#### Read Operations (cat, head)
```
Tool Call → _execute_tool()
    ↓
    Is cache_manager available?
    ↓ (yes)
    _cached_read_file()
    ↓
    Check ContentCache
    ↓
    Cache Hit? → Return cached content
    ↓ (miss)
    Execute via sandbox → Cache result → Return
```

#### Search Operations (grep, find)
```
Tool Call → _execute_tool()
    ↓
    Is cache_manager available?
    ↓ (yes)
    _cached_search()
    ↓
    Check SearchCache
    ↓
    Cache Hit? → Return cached results
    ↓ (miss)
    Execute via sandbox → Cache result → Return
```

#### Non-Cacheable Operations (ls, wc, tree)
```
Tool Call → _execute_tool()
    ↓
    Build command → Execute via sandbox → Return
```

## Usage

### Basic Usage

```python
from pathlib import Path
from app.agent.filesystem_agent import create_agent

# Create agent with new cache system
agent = create_agent(
    api_key="your_api_key",
    endpoint="https://your-endpoint.openai.azure.com",
    deployment_name="gpt-4",
    api_version="2024-02-15-preview",
    data_root=Path("./data"),
    use_new_cache=True,  # Enable new cache system
    cache_directory="tmp/cache",
    cache_size_limit=500 * 1024 * 1024,  # 500MB
    cache_content_ttl=0,  # No expiry for content
    cache_search_ttl=300,  # 5 minutes for search
)

# Use the agent
response = await agent.chat("Find all Python files in the project")

# Get cache statistics
stats = agent.get_cache_stats()
print(f"Cache size: {stats['new_cache']['disk_cache']['size']} entries")
print(f"Disk usage: {stats['new_cache']['disk_cache']['volume']} bytes")
```

### Configuration Options

#### Environment Variables

Add to `.env` file:

```bash
# New Cache Configuration
CACHE_DIRECTORY=tmp/cache
CACHE_SIZE_LIMIT=524288000  # 500MB
CACHE_CONTENT_TTL=0  # No expiry for content
CACHE_SEARCH_TTL=300  # 5 minutes
```

#### Programmatic Configuration

```python
from app.config import get_settings
from app.cache import CacheManager

# Load from settings
settings = get_settings()
cache_manager = CacheManager.default(settings)

# Or create directly
cache_manager = CacheManager(
    cache_dir="custom/cache",
    size_limit=1024 * 1024 * 1024,  # 1GB
    content_ttl=0,
    search_ttl=600,
)
```

## Migration Strategy

### Phase 1: Backward Compatibility (Current)

Default behavior keeps old cache system:

```python
# Old system (default)
agent = create_agent(
    api_key="...",
    endpoint="...",
    deployment_name="gpt-4",
    api_version="...",
    data_root=Path("./data"),
    cache_enabled=True,  # Old cache via CachedSandboxExecutor
)
```

### Phase 2: Gradual Rollout

Enable new cache with feature flag:

```python
# New system (opt-in)
agent = create_agent(
    api_key="...",
    endpoint="...",
    deployment_name="gpt-4",
    api_version="...",
    data_root=Path("./data"),
    use_new_cache=True,  # New cache via CacheManager
)
```

### Phase 3: Full Migration (Future)

Default to new cache system:

```python
# Update config.py
class Settings(BaseSettings):
    use_new_cache: bool = True  # Default to new cache
```

## Key Features

### 1. Automatic File Change Detection

```python
# First read
response1 = await agent.chat("Read config.json")
# Returns: {"version": "1.0"}

# File modified externally
Path("data/config.json").write_text('{"version": "2.0"}')

# Second read - automatically detects change
response2 = await agent.chat("Read config.json")
# Returns: {"version": "2.0"} (fresh from disk, not cached)
```

### 2. Persistent Cache

Cache survives agent restarts:

```python
# Session 1
agent1 = create_agent(..., use_new_cache=True)
await agent1.chat("Read large_file.txt")  # Cache miss
# Agent terminates

# Session 2 (later)
agent2 = create_agent(..., use_new_cache=True)
await agent2.chat("Read large_file.txt")  # Cache hit!
```

### 3. Scope-Aware Search Caching

```python
# Grep in directory
response1 = await agent.chat("Find 'TODO' in src/")
# Cached with scope = src/

# File changed in src/
Path("src/main.py").write_text("# TODO: new task")

# Next search detects change
response2 = await agent.chat("Find 'TODO' in src/")
# Cache invalidated, fresh results
```

### 4. Intelligent Cache Keys

Equivalent commands share cache:

```python
# These produce the same cache key:
grep -r "pattern" .
grep "pattern" . -r

# Result: One cached entry serves both
```

## Cache Statistics

### Retrieving Stats

```python
stats = agent.get_cache_stats()

# New cache stats
print(stats['new_cache']['disk_cache'])
# Output:
# {
#     'size': 42,           # Number of entries
#     'volume': 10485760,   # Bytes on disk (10MB)
#     'directory': 'tmp/cache'
# }

# Old cache stats (if enabled)
print(stats['old_cache'])
# Output:
# {
#     'enabled': False,  # or stats if using old cache
#     'hits': 0,
#     'misses': 0,
#     ...
# }
```

### Monitoring Cache Performance

```python
import time

# Before operation
stats_before = agent.get_cache_stats()

# Execute operation
start = time.time()
result = await agent.chat("Read large_file.txt")
elapsed = time.time() - start

# After operation
stats_after = agent.get_cache_stats()

# Calculate cache hit
cache_hit = stats_after['new_cache']['disk_cache']['size'] == \
            stats_before['new_cache']['disk_cache']['size']

print(f"Cache hit: {cache_hit}")
print(f"Execution time: {elapsed:.3f}s")
```

## Cache Operations

### Manual Cache Management

```python
# Clear all caches
await agent.cache_manager.clear_all()

# Invalidate specific file
await agent.cache_manager.invalidate_file(Path("data/config.json"))

# Invalidate directory
count = await agent.cache_manager.invalidate_directory(Path("data/logs/"))
print(f"Invalidated {count} cached entries")

# Get detailed stats
stats = agent.cache_manager.stats()
print(f"Content TTL: {stats['content_ttl']}s")
print(f"Search TTL: {stats['search_ttl']}s")
```

### Context Manager Usage

```python
# Automatic cleanup
async with CacheManager.default() as cache_mgr:
    agent = FilesystemAgent(
        client=client,
        deployment_name="gpt-4",
        data_root=Path("./data"),
        sandbox=sandbox,
        cache_manager=cache_mgr,
    )

    response = await agent.chat("Find all logs")
    # Cache automatically closed on exit
```

## Implementation Details

### File State Tracking

File state includes:
- **mtime**: Modification timestamp
- **size**: File size in bytes
- **content_hash**: MD5 hash (for files < 1MB)

Change detection:
```python
# Pseudo-code
cached_state = get_cached_state(file_path)
current_state = FileState.from_path(file_path)

if cached_state != current_state:
    # File changed, invalidate cache
    invalidate_cache(file_path)
```

### Cache Key Generation

Deterministic keys for search operations:

```python
# Input
operation = "grep"
pattern = "TODO"
scope = Path("/data/src")
options = {"recursive": True, "ignore_case": False}

# Key generation
key_data = {
    "op": "grep",
    "pattern": "TODO",
    "scope": "/absolute/path/data/src",
    "options": [("ignore_case", False), ("recursive", True)]  # Sorted
}
key = sha256(json.dumps(key_data, sort_keys=True)).hexdigest()[:16]
# Result: "_search:a1b2c3d4e5f6g7h8"
```

### LRU Eviction

When cache exceeds size limit:
1. DiskCache automatically evicts least-recently-used entries
2. Eviction is transparent to the application
3. Next access will reload from disk

## Performance Considerations

### When to Enable New Cache

**Enable when:**
- Working with large files (>1MB)
- Performing repeated searches
- Need persistent cache across sessions
- Multiple agents share the same data

**Disable when:**
- Files change frequently (< 1 second intervals)
- Data is highly dynamic
- Memory/disk space is constrained
- Working with sensitive data (cache on disk)

### Cache Size Guidelines

```python
# Small project (< 100 files)
cache_size_limit = 100 * 1024 * 1024  # 100MB

# Medium project (100-1000 files)
cache_size_limit = 500 * 1024 * 1024  # 500MB

# Large project (> 1000 files)
cache_size_limit = 2 * 1024 * 1024 * 1024  # 2GB
```

### TTL Configuration

```python
# Content cache TTL
cache_content_ttl = 0  # Recommended: rely on file state tracking

# Search cache TTL
cache_search_ttl = 300  # 5 minutes (adjust based on update frequency)
cache_search_ttl = 60   # 1 minute for rapidly changing codebases
cache_search_ttl = 1800 # 30 minutes for stable codebases
```

## Testing

Run integration tests:

```bash
# All cache integration tests
pytest tests/test_agent_cache_integration.py -v

# Specific test
pytest tests/test_agent_cache_integration.py::TestCacheIntegration::test_cached_cat_operation -v

# With coverage
pytest tests/test_agent_cache_integration.py --cov=app.agent --cov=app.cache
```

## Troubleshooting

### Cache Not Working

1. **Check if cache is enabled:**
   ```python
   stats = agent.get_cache_stats()
   print(stats['new_cache']['enabled'])  # Should not be False
   ```

2. **Verify cache directory exists:**
   ```python
   from pathlib import Path
   cache_dir = Path("tmp/cache")
   print(f"Exists: {cache_dir.exists()}")
   print(f"Writable: {cache_dir.is_dir()}")
   ```

3. **Check cache size:**
   ```python
   stats = agent.cache_manager.stats()
   print(f"Size: {stats['disk_cache']['size']}")
   print(f"Volume: {stats['disk_cache']['volume']}")
   ```

### Cache Returns Stale Data

1. **Verify file state tracking:**
   ```python
   file_path = Path("data/test.txt")
   state = await agent.cache_manager.file_state_tracker.get_state(file_path)
   print(f"Cached state: {state}")

   current = FileState.from_path(file_path)
   print(f"Current state: {current}")
   ```

2. **Manually invalidate:**
   ```python
   await agent.cache_manager.invalidate_file(file_path)
   ```

### Cache Growing Too Large

1. **Reduce size limit:**
   ```python
   # In config or create_agent
   cache_size_limit = 100 * 1024 * 1024  # 100MB instead of 500MB
   ```

2. **Clear cache periodically:**
   ```python
   # In production
   if stats['disk_cache']['volume'] > threshold:
       await agent.cache_manager.clear_all()
   ```

3. **Adjust TTL:**
   ```python
   # Shorter TTL = more frequent cache refresh
   cache_search_ttl = 60  # 1 minute instead of 5
   ```

## Best Practices

1. **Use appropriate TTL values:**
   - Content: `0` (rely on file state tracking)
   - Search: `300` (5 minutes) for most cases

2. **Monitor cache size:**
   - Log stats periodically
   - Alert if volume exceeds threshold
   - Clear cache if needed

3. **Handle errors gracefully:**
   - Cache errors should not break the agent
   - Fallback to direct execution on cache failure

4. **Test with representative data:**
   - Use realistic file sizes
   - Test with your actual codebase
   - Measure cache hit rates

5. **Consider security:**
   - Cache may contain sensitive data
   - Secure cache directory permissions
   - Clear cache when handling sensitive files

## Future Enhancements

Planned improvements:
- [ ] Memory-based L1 cache (in addition to disk L2)
- [ ] Cache warming on agent startup
- [ ] Configurable cache eviction policies
- [ ] Cache compression for large files
- [ ] Cache metrics and monitoring dashboard
- [ ] Distributed cache for multi-agent scenarios

## References

- [CACHE_IMPROVEMENT_PLAN_VI.md](CACHE_IMPROVEMENT_PLAN_VI.md) - Detailed implementation plan
- [DiskCache Documentation](https://grantjenks.com/docs/diskcache/) - Underlying cache library
- [app/cache/](../app/cache/) - Cache implementation code
- [tests/test_agent_cache_integration.py](../tests/test_agent_cache_integration.py) - Integration tests
