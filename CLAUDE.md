# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Filesystem Agent Showcase is a Python FastAPI application demonstrating AI agents that use filesystem/bash tools instead of traditional RAG pipelines. The LLM (Azure OpenAI) decides which bash commands to execute, and results are fed back in an agentic loop.

The project features a sophisticated multi-tier cache system (v3.0) with persistent disk storage and automatic file change detection, providing 50-150x performance improvements for repeated operations.

Inspired by [Vercel's approach to agentic AI](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash).

## Commands

```bash
# Development
make install          # Install dependencies with Poetry
make dev              # Run dev server with hot reload (localhost:8000)
make test             # Run all tests
make test-cov         # Run tests with coverage report
make lint             # Run ruff linting
make format           # Format code with ruff

# Run a single test
poetry run pytest tests/test_agent.py -v
poetry run pytest tests/test_agent.py::test_function_name -v

# Cache management
poetry run fs-agent warm-cache -d ./data     # Pre-populate cache
poetry run fs-agent cache-stats              # View cache statistics
poetry run fs-agent clear-cache              # Clear cache

# Container (auto-detects Podman or Docker)
make container        # Build and run container
make container-dev    # Development mode with hot reload
make container-stop   # Stop containers

# Benchmarks
poetry run python benchmarks/benchmark_v2.py --quick
```

## Architecture

### Core Agent Loop (app/agent/filesystem_agent.py)

The `FilesystemAgent.chat()` method implements the agentic loop:
1. User message → LLM with tool definitions
2. LLM returns tool calls (function calling)
3. Execute tools via `SandboxExecutor`
4. Feed results back to LLM
5. Repeat until LLM returns final response (max 10 iterations)

```
User Message → FilesystemAgent.chat() → Azure OpenAI (with BASH_TOOLS)
                     ↓                            ↓
              [tool_calls]  ←──────────── LLM Response
                     ↓
         ParallelToolOrchestrator.execute_with_strategy()
                     ↓
         SandboxExecutor.execute() → subprocess (grep/find/cat/ls/...)
                     ↓
              [results] → back to LLM → final response
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `FilesystemAgent` | `app/agent/filesystem_agent.py` | Core agent with chat() and chat_stream() methods |
| `SandboxExecutor` | `app/sandbox/executor.py` | Secure command execution with whitelist |
| `CachedSandboxExecutor` | `app/sandbox/cached_executor.py` | Executor with TTL-based result caching (v2.0 - legacy) |
| `ParallelToolOrchestrator` | `app/agent/orchestrator.py` | Concurrent tool execution |
| `CacheManager` | `app/cache/cache_manager.py` | Unified cache interface (v3.0) |
| `PersistentCache` | `app/cache/disk_cache.py` | Disk-based cache with LRU eviction (v3.0) |
| `FileStateTracker` | `app/cache/file_state.py` | File change detection (v3.0) |
| `ContentCache` | `app/cache/content_cache.py` | File content caching (v3.0) |
| `SearchCache` | `app/cache/search_cache.py` | Search result caching (v3.0) |
| `BASH_TOOLS` | `app/agent/tools/bash_tools.py` | OpenAI tool definitions (JSON schemas) |
| `Settings` | `app/config.py` | Pydantic settings from environment |

### Security Model (SandboxExecutor)

- **Whitelisted commands only**: `grep`, `find`, `cat`, `head`, `tail`, `ls`, `wc`
- **Path confinement**: All paths resolved within `DATA_ROOT_PATH`
- **Path traversal prevention**: `../` patterns blocked
- **Timeout protection**: Commands killed after `COMMAND_TIMEOUT` seconds
- **Size limits**: `MAX_FILE_SIZE` for cat, `MAX_OUTPUT_SIZE` for all output

### API Routes

| Route | Handler | Purpose |
|-------|---------|---------|
| `POST /api/chat` | `app/api/routes/chat.py` | Send message, get response with tool calls |
| `GET /api/stream/file/{path}` | `app/api/routes/stream.py` | SSE streaming file content |
| `GET /api/documents` | `app/api/routes/documents.py` | List/read/write documents |

### Configuration

All via environment variables (see `.env.example`). Key settings in `app/config.py`:

- `AZURE_OPENAI_*`: API credentials (required)
- `PARALLEL_EXECUTION`: Enable concurrent tool execution (default: true)
- `CACHE_ENABLED`: Enable v2.0 legacy cache (default: true)
- `USE_NEW_CACHE`: Enable v3.0 multi-tier cache (default: false)
- `CACHE_DIRECTORY`: Cache storage directory (default: tmp/cache)
- `CACHE_SIZE_LIMIT`: Max cache size in bytes (default: 500MB)
- `CACHE_CONTENT_TTL`: Content cache TTL (default: 0 = no expiry)
- `CACHE_SEARCH_TTL`: Search cache TTL (default: 300 seconds)
- `SANDBOX_ENABLED`: Enable security checks (default: true)

## Testing

Uses pytest with `asyncio_mode = "auto"`. Test files mirror the app structure:

```bash
# All tests
make test

# Specific test file
poetry run pytest tests/test_sandbox.py -v

# Specific test
poetry run pytest tests/test_agent.py::test_chat_returns_response -v

# With coverage
make test-cov
```

## Cache System (v3.0)

### Architecture

The new cache system provides persistent, intelligent caching:

```
FilesystemAgent
    ├── CacheManager
    │   ├── PersistentCache (L2 disk storage with LRU)
    │   ├── FileStateTracker (mtime, size, hash tracking)
    │   ├── ContentCache (file content caching)
    │   └── SearchCache (search result caching)
    └── SandboxExecutor (command execution)
```

### Cache Module Structure

```
app/cache/
├── __init__.py           # Exports CacheManager, PersistentCache, etc.
├── cache_manager.py      # Unified cache interface
├── disk_cache.py         # PersistentCache implementation
├── file_state.py         # FileStateTracker implementation
├── content_cache.py      # ContentCache implementation
├── search_cache.py       # SearchCache implementation
└── warmup.py             # Cache pre-population tool
```

### Key Features

1. **Persistent Storage**: Cache survives restarts (DiskCache backend)
2. **Automatic Invalidation**: Detects file changes via FileStateTracker
3. **Content-Aware Keys**: Equivalent commands share cache entries
4. **Scope-Aware Invalidation**: Directory changes invalidate related searches
5. **LRU Eviction**: Automatic cleanup when size limit is reached

### Using the Cache

```python
from app.agent.filesystem_agent import create_agent

# Create agent with new cache
agent = create_agent(
    api_key="...",
    endpoint="...",
    deployment_name="gpt-4",
    api_version="...",
    data_root=Path("./data"),
    use_new_cache=True,  # Enable v3.0 cache
)

# Get cache stats
stats = agent.get_cache_stats()
print(stats['new_cache'])

# Manually invalidate
await agent.cache_manager.invalidate_file(Path("data/file.txt"))
await agent.cache_manager.clear_all()
```

### Cached Operations

- `cat` - Read entire file content
- `head` - Read first N lines
- `grep` - Search for patterns
- `find` - Find files by name

Operations NOT cached (fast or frequently changing):
- `ls`, `wc`, `tree`

### Testing Cache Components

```bash
# Test cache manager
poetry run pytest tests/test_cache_manager.py -v

# Test individual components
poetry run pytest tests/test_disk_cache.py -v
poetry run pytest tests/test_file_state.py -v
poetry run pytest tests/test_content_cache.py -v
poetry run pytest tests/test_search_cache.py -v

# Test agent integration
poetry run pytest tests/test_agent_cache_integration.py -v
```

### Cache Testing Guidelines

When testing cache functionality:

1. **Use temporary cache directory**: Always use a test-specific cache dir
   ```python
   cache_manager = CacheManager(cache_dir="tmp/test_cache")
   ```

2. **Clean up after tests**: Use fixtures or context managers
   ```python
   @pytest.fixture
   async def cache_manager():
       manager = CacheManager(cache_dir="tmp/test_cache")
       yield manager
       await manager.clear_all()
       manager.close()
   ```

3. **Mock file operations**: Use temporary files for state tracking tests
   ```python
   tmp_file = tmp_path / "test.txt"
   tmp_file.write_text("content")
   ```

4. **Test cache invalidation**: Verify that file changes trigger invalidation
   ```python
   # Read file (cache miss)
   content1 = await cache.get_content(file_path, loader)

   # Modify file
   file_path.write_text("new content")

   # Read again (should be cache miss due to invalidation)
   content2 = await cache.get_content(file_path, loader)
   assert content2 == "new content"
   ```

5. **Test concurrent operations**: Use asyncio.gather for parallel tests
   ```python
   results = await asyncio.gather(
       cache.get("key1"),
       cache.set("key2", "value"),
       cache.delete("key3"),
   )
   ```

### Documentation

- [Quick Start](docs/CACHE_QUICKSTART.md) - Get started in 3 lines
- [Migration Guide](docs/CACHE_MIGRATION_GUIDE.md) - Migrate from v2.0 cache
- [Integration Guide](docs/CACHE_INTEGRATION_GUIDE.md) - Complete documentation
- [Cache Manager API](docs/CACHE_MANAGER.md) - API reference
- [CLI Usage](docs/CACHE_CLI_USAGE.md) - Command-line tools

## Adding New Tools

1. Add tool definition to `BASH_TOOLS` in `app/agent/tools/bash_tools.py` (OpenAI function calling format)
2. Add command to `ALLOWED_COMMANDS` in `app/sandbox/executor.py`
3. Implement `build_command()` case in `bash_tools.py`
4. Add tests in `tests/test_tools.py`
5. Consider if the tool should be cached (update `_execute_tool()` in `filesystem_agent.py` if needed)

## Development Guidelines

### Parallel Execution Strategy

When working on this codebase, **always prefer parallel execution** to speed up development:

1. **Multi-file changes**: When modifying multiple independent files, spawn parallel agents for each file or logical group
2. **Testing**: Run tests in parallel with independent test files
3. **Code review tasks**: Analyze multiple components simultaneously
4. **Refactoring**: Apply similar changes across files concurrently

**Example parallel task breakdown:**
```
Task: Implement cache fixes F1-F4

Spawn in parallel:
├── Agent 1: F1 fix (content_cache.py + filesystem_agent.py)
├── Agent 2: F2 fix (search_cache.py - scope tracking)
├── Agent 3: F3 fix (TTL application across cache_manager.py)
└── Agent 4: F4 fix (path boundary in content_cache.py)
```

**When NOT to parallelize:**
- Sequential dependencies (e.g., create file A before importing in file B)
- Shared state modifications that could conflict
- Database migrations or schema changes

### Implementation Workflow

For complex features:
1. **Plan first**: Create implementation plan with clear task breakdown
2. **Identify parallelizable work**: Group independent changes
3. **Spawn agents**: Use Task tool with multiple parallel agents
4. **Integrate**: Merge results and run integration tests
5. **Validate**: Run full test suite

### Code Quality Standards

- All new code must have corresponding tests
- Maintain >80% test coverage for cache modules
- Follow existing code style (ruff formatting)
- Update documentation for API changes
