# Cache CLI Usage Guide

This document provides comprehensive instructions for using the filesystem-agent-showcase cache management CLI.

## Overview

The cache CLI provides commands for managing the application's file content and search result caches. These tools help optimize performance by pre-populating caches and providing maintenance capabilities.

## Installation

After installing the project dependencies, the CLI is available via the `fs-agent` command:

```bash
# Install dependencies
poetry install

# Verify CLI is available
poetry run fs-agent --help
```

## Commands

### 1. warm-cache

Pre-populate the cache with file contents from a directory.

**Purpose**: Scan a directory for text files and load their contents into the cache, improving performance for subsequent file operations.

**Usage**:

```bash
fs-agent warm-cache [OPTIONS]
```

**Options**:

- `-d, --directory PATH` (required): Directory to scan and cache files from
- `-r, --recursive`: Recursively scan subdirectories (default: True)
- `-p, --pattern TEXT`: Glob pattern to match files (default: *)
- `-c, --concurrency INTEGER`: Maximum concurrent cache operations (1-50, default: 10)
- `--cache-dir PATH`: Custom cache directory (default: from config)
- `-q, --quiet`: Suppress progress output
- `-v, --verbose`: Enable verbose logging

**Examples**:

```bash
# Cache all text files in ./data directory (recursive by default)
poetry run fs-agent warm-cache -d ./data

# Cache only Python files
poetry run fs-agent warm-cache -d ./src -p "*.py"

# Cache only JavaScript/TypeScript files
poetry run fs-agent warm-cache -d ./frontend -p "*.{js,ts,jsx,tsx}"

# Cache a single directory
poetry run fs-agent warm-cache -d ./config

# Use custom concurrency for faster caching
poetry run fs-agent warm-cache -d ./large-project -c 20

# Use custom cache directory
poetry run fs-agent warm-cache -d ./data --cache-dir /tmp/custom-cache

# Quiet mode (no progress output)
poetry run fs-agent warm-cache -d ./data --quiet

# Verbose mode for debugging
poetry run fs-agent -v warm-cache -d ./data
```

**Supported File Types**:

The warmup automatically detects and caches the following text file types:

- **Programming Languages**: .py, .js, .ts, .jsx, .tsx, .java, .c, .cpp, .go, .rs, .rb, .php, .swift, .kt, .scala
- **Shell Scripts**: .sh, .bash, .zsh, .fish, .ps1, .bat, .cmd
- **Web Files**: .html, .css, .scss, .sass, .less, .xml, .svg
- **Data Files**: .json, .yaml, .yml, .toml, .ini, .conf, .csv, .tsv
- **Documentation**: .md, .markdown, .rst, .txt, .log
- **Build Files**: Dockerfile, Makefile, Rakefile, Gemfile, .lock

**Skipped Directories**:

The following directories are automatically skipped to avoid caching unnecessary files:

- `__pycache__`, `.git`, `.svn`, `.hg`
- `node_modules`, `.venv`, `venv`
- `dist`, `build`, `target`, `bin`, `obj`
- `.pytest_cache`, `.mypy_cache`, `.tox`
- `.next`, `.nuxt`

**Output**:

```
Starting cache warmup...
  Directory: /Users/user/project/data
  Recursive: True
  Pattern: *
  Concurrency: 10
  Cache location: /Users/user/project/tmp/cache

Progress: 10/150 (6.7%) - document.txt
Progress: 20/150 (13.3%) - config.yaml
...
Progress: 150/150 (100.0%) - final.md

Cache Warmup Complete!

Cache Warmup Statistics:
  Files Processed: 150
  Succeeded: 148 (98.7%)
  Failed: 2
  Data Cached: 2.45 MB
  Top File Types:
    .py: 65 files
    .md: 32 files
    .json: 28 files
    .yaml: 15 files
    .txt: 8 files
  Errors: 2 (see logs for details)

Current Cache Statistics:
  Total entries: 148
  Disk usage: 2.45 MB
  Cache directory: /Users/user/project/tmp/cache
```

---

### 2. clear-cache

Clear all caches and remove all cached data.

**Purpose**: Remove all cached file contents, search results, and file state tracking data. This is useful for forcing a complete cache refresh or freeing up disk space.

**Usage**:

```bash
fs-agent clear-cache [OPTIONS]
```

**Options**:

- `--cache-dir PATH`: Custom cache directory (default: from config)
- `-f, --force`: Skip confirmation prompt
- `-v, --verbose`: Enable verbose logging

**Examples**:

```bash
# Clear cache with confirmation prompt
poetry run fs-agent clear-cache

# Clear cache without confirmation (useful for scripts)
poetry run fs-agent clear-cache --force

# Clear custom cache directory
poetry run fs-agent clear-cache --cache-dir /tmp/custom-cache -f

# Verbose mode
poetry run fs-agent -v clear-cache -f
```

**Output**:

```
Current Cache Statistics:
  Total entries: 148
  Disk usage: 2.45 MB
  Cache directory: /Users/user/project/tmp/cache

Are you sure you want to clear ALL cache data? [y/N]: y
Cache cleared successfully!
Current entries: 0
```

**Warning**: This operation is irreversible. All cached data will be permanently removed.

---

### 3. cache-stats

Display comprehensive cache statistics.

**Purpose**: Show information about cache size, disk usage, configuration, and performance metrics.

**Usage**:

```bash
fs-agent cache-stats [OPTIONS]
```

**Options**:

- `--cache-dir PATH`: Custom cache directory (default: from config)
- `--json`: Output statistics as JSON
- `-v, --verbose`: Enable verbose logging

**Examples**:

```bash
# Display cache statistics (human-readable)
poetry run fs-agent cache-stats

# Output as JSON for scripting
poetry run fs-agent cache-stats --json

# Check custom cache directory
poetry run fs-agent cache-stats --cache-dir /tmp/custom-cache

# Verbose mode
poetry run fs-agent -v cache-stats
```

**Output (Human-Readable)**:

```
Cache Statistics

Storage:
  Total entries: 148
  Disk usage: 2.45 MB
  Cache directory: /Users/user/project/tmp/cache

Configuration:
  Size limit: 524288000 bytes
             (500.00 MB)
  Eviction policy: least-recently-used
  Content TTL: 0 seconds
  Search TTL: 300 seconds

Cache Usage: 0.5%
████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

**Output (JSON)**:

```json
{
  "disk_cache": {
    "size": 148,
    "volume": 2569216,
    "directory": "/Users/user/project/tmp/cache"
  },
  "content_ttl": 0,
  "search_ttl": 300,
  "configuration": {
    "cache_directory": "/Users/user/project/tmp/cache",
    "size_limit": 524288000,
    "eviction_policy": "least-recently-used"
  }
}
```

---

## Common Workflows

### Initial Cache Warmup

When starting to work with a new project or after clearing the cache:

```bash
# Warm cache for the entire project
poetry run fs-agent warm-cache -d ./data -c 20

# Check cache statistics
poetry run fs-agent cache-stats
```

### Targeted Cache Warmup

For specific file types or directories:

```bash
# Cache only Python source files
poetry run fs-agent warm-cache -d ./app -p "*.py"

# Cache configuration files
poetry run fs-agent warm-cache -d ./config

# Cache documentation
poetry run fs-agent warm-cache -d ./docs -p "*.md"
```

### Cache Maintenance

Regular maintenance tasks:

```bash
# Check current cache status
poetry run fs-agent cache-stats

# Clear and rebuild cache
poetry run fs-agent clear-cache --force
poetry run fs-agent warm-cache -d ./data
```

### Scripting

Use the CLI in scripts for automation:

```bash
#!/bin/bash
# cache_maintenance.sh

set -e

echo "Clearing old cache..."
poetry run fs-agent clear-cache --force

echo "Warming cache for source code..."
poetry run fs-agent warm-cache -d ./app -p "*.py" -c 20

echo "Warming cache for documentation..."
poetry run fs-agent warm-cache -d ./docs -p "*.md" -c 10

echo "Cache statistics:"
poetry run fs-agent cache-stats --json | jq '.disk_cache'

echo "Cache maintenance complete!"
```

---

## Performance Tuning

### Concurrency Settings

The `-c, --concurrency` option controls how many files are cached simultaneously:

- **Low concurrency (5-10)**: Safer for systems with limited I/O or memory
- **Medium concurrency (10-20)**: Good balance for most systems
- **High concurrency (20-50)**: Faster on systems with fast SSDs and plenty of memory

**Example**:

```bash
# Conservative (good for HDDs)
poetry run fs-agent warm-cache -d ./data -c 5

# Balanced (default)
poetry run fs-agent warm-cache -d ./data -c 10

# Aggressive (good for fast SSDs)
poetry run fs-agent warm-cache -d ./data -c 30
```

### Pattern Optimization

Use specific patterns to reduce scanning time:

```bash
# Instead of scanning all files
poetry run fs-agent warm-cache -d ./project

# Target specific file types
poetry run fs-agent warm-cache -d ./project -p "*.{py,js,ts,md}"
```

---

## Troubleshooting

### Permission Errors

If you encounter permission errors:

```bash
# Check cache directory permissions
ls -la tmp/cache

# Use custom cache directory with write permissions
poetry run fs-agent warm-cache -d ./data --cache-dir ~/tmp/cache
```

### Memory Issues

If the system runs out of memory during warmup:

```bash
# Reduce concurrency
poetry run fs-agent warm-cache -d ./data -c 3

# Process subdirectories separately
poetry run fs-agent warm-cache -d ./data/subdir1
poetry run fs-agent warm-cache -d ./data/subdir2
```

### Encoding Errors

Files with non-UTF-8 encoding will fail to cache but won't stop the process. Check logs for details:

```bash
poetry run fs-agent -v warm-cache -d ./data 2>&1 | grep "Failed to cache"
```

---

## Configuration

The CLI respects environment variables and `.env` file settings:

```bash
# .env file
CACHE_DIRECTORY=tmp/cache
CACHE_SIZE_LIMIT=524288000  # 500MB
CACHE_CONTENT_TTL=0         # No expiry
CACHE_SEARCH_TTL=300        # 5 minutes
```

You can override these with command-line options:

```bash
poetry run fs-agent warm-cache -d ./data --cache-dir /custom/cache
```

---

## Integration with Application

The cache CLI is designed to work alongside the main application. You can:

1. **Pre-warm cache before starting the application**:
   ```bash
   poetry run fs-agent warm-cache -d ./data
   poetry run uvicorn app.main:app
   ```

2. **Schedule periodic cache maintenance**:
   ```bash
   # crontab
   0 2 * * * cd /path/to/project && poetry run fs-agent clear-cache --force && poetry run fs-agent warm-cache -d ./data
   ```

3. **Monitor cache usage**:
   ```bash
   watch -n 60 'poetry run fs-agent cache-stats'
   ```

---

## Best Practices

1. **Warm cache after deployment**: Pre-populate the cache to avoid cold start latency
2. **Use specific patterns**: Only cache files you actually need
3. **Monitor cache usage**: Check stats regularly to ensure cache is effective
4. **Clear stale cache**: Periodically clear and rebuild cache to remove outdated entries
5. **Adjust concurrency**: Tune based on your system's capabilities
6. **Use quiet mode in scripts**: Add `--quiet` flag for cleaner script output

---

## API Usage

You can also use the warmup functions programmatically:

```python
import asyncio
from pathlib import Path
from app.cache import CacheManager, warm_cache, warm_cache_selective

async def main():
    # Initialize cache manager
    cache_manager = CacheManager.default()

    # Warm cache for a directory
    stats = await warm_cache(
        cache_manager.content_cache,
        directory=Path("./data"),
        recursive=True,
        pattern="*.py",
        concurrency=10
    )

    print(f"Cached {stats.files_succeeded} files")
    print(f"Data cached: {stats.bytes_cached / (1024 * 1024):.2f} MB")

    # Or warm cache for specific files
    files_to_cache = [
        Path("./config.yaml"),
        Path("./README.md"),
        Path("./app/main.py"),
    ]

    stats = await warm_cache_selective(
        cache_manager.content_cache,
        file_paths=files_to_cache,
        concurrency=5
    )

    cache_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## See Also

- [CACHE_IMPROVEMENT_PLAN_VI.md](./CACHE_IMPROVEMENT_PLAN_VI.md) - Detailed cache architecture
- [app/cache/warmup.py](../app/cache/warmup.py) - Warmup implementation
- [app/cli.py](../app/cli.py) - CLI implementation
