# Cache System Fix Plan

## Overview

This document outlines the fixes for cache correctness issues identified in the v3.0 multi-tier cache system.

---

## Findings Summary

| ID | Severity | Issue | Location |
|----|----------|-------|----------|
| F1 | **HIGH** | head/cat share path-only cache key (cache poisoning) | `filesystem_agent.py:169`, `content_cache.py:114` |
| F2 | **HIGH** | Directory search cache ignores file content changes | `search_cache.py:221`, `file_state.py:47` |
| F3 | **MEDIUM** | TTL settings stored but not applied | `cache_manager.py:122`, `content_cache.py:128` |
| F4 | **MEDIUM** | invalidate_directory uses raw prefix matching | `content_cache.py:195` |

---

## Design Decisions

### Q1: Should head bypass caching entirely, or cache full content and slice?

**Decision: Cache full content, slice per request**

Rationale:
- More efficient: one disk read serves multiple operations (cat, head -n 10, head -n 50)
- Simpler invalidation: single entry per file
- Memory impact acceptable: files are already size-limited (10MB max)

Implementation:
- ContentCache always caches full file content
- `_cached_read_file()` applies head/tail slicing AFTER cache retrieval

### Q2: For search invalidation, per-file tracking or watcher-based?

**Decision: Hybrid approach with recursive file tracking as default**

Rationale:
- Per-file tracking ensures correctness (mandatory)
- Watcher-based is optional enhancement for real-time invalidation
- For small-medium directories (<1000 files), per-file tracking is acceptable

Implementation:
- Track file states for all files in search scope
- Store scope file list + states with search result
- On cache hit, verify all tracked files are unchanged
- Optional: watchdog integration for proactive invalidation

### Q3: Should TTL settings drive actual expirations or be removed?

**Decision: Apply TTL settings as configured**

Rationale:
- Configuration exists for a reason
- Content TTL=0 means "no expiry, rely on file state"
- Search TTL provides periodic refresh even without detected changes

Implementation:
- Pass `content_ttl` to ContentCache
- Pass `search_ttl` to SearchCache
- Apply TTL in `set()` calls

### Q4: Prefix matching vs path-segment boundaries?

**Decision: Enforce path-segment boundaries**

Rationale:
- Current behavior is a bug (can invalidate unrelated paths)
- `/data` should NOT match `/data2` or `/data_backup`
- `/data` SHOULD match `/data/subdir/file.txt`

Implementation:
- Check that path starts with `prefix/` OR equals `prefix` exactly
- Use `pathlib` for proper path comparison

---

## Fix Plan

### Phase 1: Fix High Priority Issues

#### Fix F1: head/cat Cache Key Collision

**Files to modify:**
- `app/cache/content_cache.py`
- `app/agent/filesystem_agent.py`

**Changes:**

1. **ContentCache: Always cache full file content**

```python
# content_cache.py - Update get_content to always return full content
async def get_content(
    self,
    path: Path,
    loader: Callable[[Path], Awaitable[str]],
    ttl: Optional[float] = None,  # Add TTL parameter
) -> str:
    """Get full file content (always caches complete file)."""
    resolved = path.resolve()
    key = f"{self._content_prefix}{resolved}"

    # Check if cached and not stale
    if not await self._tracker.is_stale(resolved):
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug(f"Cache HIT: {path}")
            return cached

    # Cache miss or stale - load FULL content
    content = await loader(path)

    # Update cache with TTL
    expire = ttl if ttl and ttl > 0 else None
    await self._cache.set(key, content, expire=expire)
    await self._tracker.update_state(resolved)

    return content
```

2. **FilesystemAgent: Cache full content, slice for head**

```python
# filesystem_agent.py - Update _cached_read_file
async def _cached_read_file(self, tool_call: ToolCall) -> ExecutionResult:
    """Execute a file read operation with caching."""
    path_str = tool_call.arguments.get("path", "")
    file_path = (self.data_root / path_str).resolve()

    try:
        # Define loader that reads FULL file content
        async def load_full_file(p: Path) -> str:
            # Always use cat to get full content
            command = build_command("cat", {"path": path_str})
            result = await self.sandbox.execute(command)
            if result.success:
                return result.stdout
            else:
                raise Exception(f"Failed to read file: {result.stderr}")

        # Get FULL content from cache
        full_content = await self.cache_manager.content_cache.get_content(
            file_path,
            load_full_file,
            ttl=self.cache_manager._content_ttl
        )

        # Apply operation-specific processing
        if tool_call.name == "head":
            lines = tool_call.arguments.get("lines", 10)
            content = "\n".join(full_content.split("\n")[:lines])
        elif tool_call.name == "tail":
            lines = tool_call.arguments.get("lines", 10)
            content = "\n".join(full_content.split("\n")[-lines:])
        else:
            content = full_content

        # Build command string for logging
        command = build_command(tool_call.name, tool_call.arguments)

        return ExecutionResult(
            success=True,
            stdout=content,
            stderr="",
            return_code=0,
            command=command,
            error=None,
        )
    except Exception as e:
        # ... error handling
```

---

#### Fix F2: Search Cache Stale for File Content Changes

**Files to modify:**
- `app/cache/search_cache.py`
- `app/cache/file_state.py`

**Changes:**

1. **SearchCache: Track all files in scope**

```python
# search_cache.py - Update to track file states

from dataclasses import dataclass
from typing import Dict

@dataclass
class ScopedSearchResult:
    """Cached search result with file state tracking."""
    result: str
    file_states: Dict[str, tuple]  # path -> (mtime, size, hash)

async def get_search_result(
    self,
    operation: str,
    pattern: str,
    scope: Path,
    options: dict,
) -> Optional[str]:
    """Get cached search result if scope hasn't changed."""
    key = self._make_key(operation, pattern, scope, options)

    # Get cached entry
    cached = await self._cache.get(key)
    if cached is None:
        return None

    # Validate all tracked file states
    if isinstance(cached, ScopedSearchResult):
        if await self._is_scope_stale_detailed(scope, cached.file_states):
            await self._cache.delete(key)
            logger.debug(f"Cache STALE (file changed): {operation} {scope}")
            return None
        return cached.result

    # Legacy cache entry without file tracking
    return None

async def set_search_result(
    self,
    operation: str,
    pattern: str,
    scope: Path,
    options: dict,
    result: str,
    ttl: Optional[float] = None,
) -> None:
    """Cache search result with file state tracking."""
    key = self._make_key(operation, pattern, scope, options)

    # Collect file states for all files in scope
    file_states = await self._collect_file_states(scope)

    # Store as ScopedSearchResult
    entry = ScopedSearchResult(result=result, file_states=file_states)

    expire = ttl if ttl and ttl > 0 else 300  # Default 5 min
    await self._cache.set(key, entry, expire=expire)

    logger.debug(f"Cache SET: {operation} scope={scope} files={len(file_states)}")

async def _collect_file_states(self, scope: Path) -> Dict[str, tuple]:
    """Collect current state of all files in scope."""
    file_states = {}

    if scope.is_file():
        state = FileState.from_path(scope, hash_content=True)
        file_states[str(scope)] = (state.mtime, state.size, state.content_hash)
    else:
        # Recursively collect file states
        for file_path in scope.rglob("*"):
            if file_path.is_file():
                try:
                    state = FileState.from_path(file_path, hash_content=True)
                    file_states[str(file_path)] = (state.mtime, state.size, state.content_hash)
                except (OSError, IOError):
                    pass  # Skip inaccessible files

    return file_states

async def _is_scope_stale_detailed(
    self,
    scope: Path,
    cached_states: Dict[str, tuple]
) -> bool:
    """Check if any file in scope has changed."""
    current_files = set()

    if scope.is_file():
        current_files.add(str(scope))
    else:
        for file_path in scope.rglob("*"):
            if file_path.is_file():
                current_files.add(str(file_path))

    cached_files = set(cached_states.keys())

    # Check for added or deleted files
    if current_files != cached_files:
        return True

    # Check each file for changes
    for file_path_str, (mtime, size, content_hash) in cached_states.items():
        file_path = Path(file_path_str)
        try:
            current_state = FileState.from_path(file_path, hash_content=True)
            if (current_state.mtime != mtime or
                current_state.size != size or
                current_state.content_hash != content_hash):
                return True
        except FileNotFoundError:
            return True  # File was deleted

    return False
```

---

### Phase 2: Fix Medium Priority Issues

#### Fix F3: Apply TTL Settings

**Files to modify:**
- `app/cache/cache_manager.py`
- `app/cache/content_cache.py`
- `app/cache/search_cache.py`
- `app/agent/filesystem_agent.py`

**Changes:**

1. **Pass TTL to ContentCache and SearchCache constructors**

```python
# cache_manager.py
self.content_cache = ContentCache(
    disk_cache=self.persistent_cache,
    state_tracker=self.file_state_tracker,
    default_ttl=content_ttl,  # Add default TTL
)

self.search_cache = SearchCache(
    disk_cache=self.persistent_cache,
    state_tracker=self.file_state_tracker,
    default_ttl=search_ttl,  # Add default TTL
)
```

2. **ContentCache: Use TTL in set()**

```python
# content_cache.py
def __init__(self, disk_cache, state_tracker, default_ttl: float = 0):
    self._default_ttl = default_ttl

async def get_content(self, path, loader, ttl: Optional[float] = None):
    # ...
    effective_ttl = ttl if ttl is not None else self._default_ttl
    expire = effective_ttl if effective_ttl > 0 else None
    await self._cache.set(key, content, expire=expire)
```

3. **SearchCache: Use configured TTL**

```python
# search_cache.py
def __init__(self, disk_cache, state_tracker, default_ttl: float = 300):
    self._default_ttl = default_ttl

async def set_search_result(self, ..., ttl: Optional[float] = None):
    effective_ttl = ttl if ttl is not None else self._default_ttl
    await self._cache.set(key, entry, expire=effective_ttl)
```

---

#### Fix F4: Path-Segment Boundary Matching

**Files to modify:**
- `app/cache/content_cache.py`

**Changes:**

```python
# content_cache.py - Update invalidate_directory

async def invalidate_directory(self, directory: Path) -> int:
    """
    Invalidate all cached files in a directory.

    Uses proper path-segment boundary matching:
    - /data will match /data/file.txt and /data/subdir/file.txt
    - /data will NOT match /data2 or /data_backup
    """
    count = 0
    dir_resolved = directory.resolve()
    dir_str = str(dir_resolved)

    for key in self._cache._cache.iterkeys():
        if not key.startswith(self._content_prefix):
            continue

        # Extract the path from the cache key
        cached_path_str = key[len(self._content_prefix):]
        cached_path = Path(cached_path_str)

        # Check if cached_path is within directory using proper path comparison
        try:
            cached_path.relative_to(dir_resolved)
            # If no exception, cached_path is inside directory
            await self._cache.delete(key)
            count += 1
        except ValueError:
            # Not within directory, skip
            pass

    logger.debug(f"Cache INVALIDATED directory: {directory} ({count} entries)")
    return count
```

---

## Implementation Order

1. **Phase 1A: Fix F1 (head/cat collision)** - Critical for correctness
   - Modify `content_cache.py`
   - Modify `filesystem_agent.py`
   - Add tests

2. **Phase 1B: Fix F2 (search scope staleness)** - Critical for correctness
   - Add `ScopedSearchResult` dataclass
   - Modify `search_cache.py`
   - Add tests

3. **Phase 2A: Fix F3 (apply TTL settings)** - Configuration correctness
   - Modify `cache_manager.py`
   - Modify `content_cache.py`
   - Modify `search_cache.py`
   - Add tests

4. **Phase 2B: Fix F4 (path-segment matching)** - Bug fix
   - Modify `content_cache.py`
   - Add tests

---

## Test Plan

### F1 Tests

```python
async def test_head_does_not_poison_cat():
    """Ensure head result doesn't affect subsequent cat."""
    # Create file with 100 lines
    file_path = tmp_path / "test.txt"
    file_path.write_text("\n".join(f"line{i}" for i in range(100)))

    # Call head -n 10
    head_result = await agent.chat("Show first 10 lines of test.txt")
    assert len(head_result.split("\n")) == 10

    # Call cat - should return ALL 100 lines
    cat_result = await agent.chat("Show contents of test.txt")
    assert len(cat_result.split("\n")) == 100

async def test_different_head_counts():
    """Ensure different head line counts work correctly."""
    # head -n 5 should return 5 lines
    # head -n 50 should return 50 lines (even if cached)
```

### F2 Tests

```python
async def test_search_detects_file_content_change():
    """Ensure grep results invalidate when file content changes."""
    # Create initial file
    file_path.write_text("original content")

    # Search
    result1 = await agent.chat("Search for 'original' in data")
    assert "original" in result1

    # Modify file
    file_path.write_text("modified content with TODO")

    # Search again - should NOT return cached result
    result2 = await agent.chat("Search for 'TODO' in data")
    assert "TODO" in result2

async def test_search_detects_new_file():
    """Ensure new files in scope invalidate search cache."""
```

### F3 Tests

```python
async def test_content_ttl_applies():
    """Ensure content_ttl is applied to cache entries."""

async def test_search_ttl_applies():
    """Ensure search_ttl is applied to cache entries."""
```

### F4 Tests

```python
async def test_invalidate_directory_respects_boundaries():
    """Ensure /data doesn't invalidate /data2."""
    # Cache /data/file.txt
    # Cache /data2/file.txt
    # Invalidate /data
    # Verify /data2/file.txt still cached
```

---

## Risk Assessment

| Fix | Risk Level | Mitigation |
|-----|------------|------------|
| F1 | Medium | Full content caching increases memory; mitigated by existing file size limits |
| F2 | Medium | Per-file tracking slower for large dirs; add file count limit or warning |
| F3 | Low | Existing behavior maintained if TTL=0 |
| F4 | Low | More restrictive matching; no false positives |

---

## Performance Impact

### F1: head/cat fix
- **Memory**: Slightly higher (full files cached instead of partial)
- **Speed**: Faster for head after cat (no re-read)
- **Net**: Positive for typical use cases

### F2: search scope tracking
- **Memory**: Higher (store file states per search)
- **Speed**: Slower cache validation for large directories
- **Mitigation**:
  - Limit tracked files to 1000 per scope
  - Use directory mtime as fast first-pass check
  - Log warning for large scopes

### F3: TTL application
- **No significant impact** - just enables existing configuration

### F4: path boundary matching
- **No significant impact** - same iteration, different comparison

---

## Rollout Plan

1. Implement fixes in feature branch
2. Run full test suite (300+ tests)
3. Add new tests for each fix
4. Benchmark performance impact
5. Code review
6. Merge to main
7. Monitor cache hit rates and performance

---

## Success Criteria

- [ ] F1: `head` and `cat` return correct content independently
- [ ] F2: File content changes invalidate search results
- [ ] F3: TTL settings from config are applied
- [ ] F4: Path invalidation respects segment boundaries
- [ ] All existing tests pass
- [ ] New tests for each fix pass
- [ ] No significant performance regression
