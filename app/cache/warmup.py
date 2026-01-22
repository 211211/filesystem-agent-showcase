"""
Cache warmup utilities for pre-populating caches with file contents.

This module provides functions to recursively scan directories and pre-populate
the cache with file contents, improving performance for subsequent file operations.
"""

import asyncio
import logging
from pathlib import Path
from typing import Set, Optional, Dict, Any
from collections import Counter

logger = logging.getLogger(__name__)

# Common text file extensions that should be cached
TEXT_EXTENSIONS = {
    # Programming languages
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp',
    '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.m', '.mm',
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.psm1', '.bat', '.cmd',

    # Web & Data
    '.html', '.htm', '.css', '.scss', '.sass', '.less', '.xml', '.svg',
    '.json', '.yaml', '.yml', '.toml', '.ini', '.conf', '.config',

    # Documentation & Text
    '.md', '.markdown', '.rst', '.txt', '.text', '.log',
    '.tex', '.adoc', '.asciidoc', '.org',

    # Configuration & Build
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
    'Dockerfile', 'Makefile', 'Rakefile', 'Gemfile', 'Podfile',
    '.lock', '.sum', '.gradle', '.properties',

    # Data & Serialization
    '.csv', '.tsv', '.sql', '.graphql', '.proto',
}

# Files/directories to skip during warmup
SKIP_PATTERNS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules', '.venv', 'venv',
    'dist', 'build', '.pytest_cache', '.mypy_cache', '.tox', '.coverage',
    '.next', '.nuxt', 'target', 'bin', 'obj', '.DS_Store',
}


class WarmupStats:
    """Statistics for cache warmup operations."""

    def __init__(self):
        self.files_processed = 0
        self.files_succeeded = 0
        self.files_failed = 0
        self.bytes_cached = 0
        self.errors: Dict[str, str] = {}
        self.file_types: Counter = Counter()

    def add_success(self, file_path: Path, size: int):
        """Record a successful cache operation."""
        self.files_processed += 1
        self.files_succeeded += 1
        self.bytes_cached += size
        self.file_types[file_path.suffix or '(no extension)'] += 1

    def add_failure(self, file_path: Path, error: str):
        """Record a failed cache operation."""
        self.files_processed += 1
        self.files_failed += 1
        self.errors[str(file_path)] = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to a dictionary."""
        return {
            'files_processed': self.files_processed,
            'files_succeeded': self.files_succeeded,
            'files_failed': self.files_failed,
            'bytes_cached': self.bytes_cached,
            'bytes_cached_mb': round(self.bytes_cached / (1024 * 1024), 2),
            'file_types': dict(self.file_types.most_common()),
            'errors_count': len(self.errors),
        }

    def __str__(self) -> str:
        """Human-readable statistics summary."""
        mb_cached = self.bytes_cached / (1024 * 1024)
        success_rate = (self.files_succeeded / self.files_processed * 100) if self.files_processed > 0 else 0

        lines = [
            f"Cache Warmup Statistics:",
            f"  Files Processed: {self.files_processed}",
            f"  Succeeded: {self.files_succeeded} ({success_rate:.1f}%)",
            f"  Failed: {self.files_failed}",
            f"  Data Cached: {mb_cached:.2f} MB",
        ]

        if self.file_types:
            lines.append(f"  Top File Types:")
            for ext, count in self.file_types.most_common(5):
                lines.append(f"    {ext}: {count} files")

        if self.errors:
            lines.append(f"  Errors: {len(self.errors)} (see logs for details)")

        return '\n'.join(lines)


def is_text_file(file_path: Path) -> bool:
    """
    Determine if a file is a text file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        True if the file appears to be a text file, False otherwise
    """
    # Check extension (case-insensitive)
    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    # Check exact filename matches (e.g., Makefile, Dockerfile)
    if file_path.name in TEXT_EXTENSIONS:
        return True

    return False


def should_skip(path: Path) -> bool:
    """
    Determine if a path should be skipped during scanning.

    Args:
        path: Path to check

    Returns:
        True if the path should be skipped, False otherwise
    """
    # Check if any part of the path matches skip patterns
    for part in path.parts:
        if part in SKIP_PATTERNS:
            return True

    return False


async def find_text_files(
    directory: Path,
    recursive: bool = True,
    pattern: str = '*',
) -> list[Path]:
    """
    Find all text files in a directory matching the given pattern.

    Args:
        directory: Directory to search
        recursive: Whether to search recursively in subdirectories
        pattern: Glob pattern to match files (default: '*' for all files)

    Returns:
        List of Path objects for text files found

    Example:
        >>> files = await find_text_files(Path('./data'), recursive=True)
        >>> print(f"Found {len(files)} text files")
    """
    files = []

    try:
        if recursive:
            iterator = directory.rglob(pattern)
        else:
            iterator = directory.glob(pattern)

        for path in iterator:
            # Skip non-files
            if not path.is_file():
                continue

            # Skip unwanted patterns
            if should_skip(path):
                logger.debug(f"Skipping: {path} (matches skip pattern)")
                continue

            # Only include text files
            if is_text_file(path):
                files.append(path)
            else:
                logger.debug(f"Skipping: {path} (not a text file)")

    except Exception as e:
        logger.error(f"Error scanning directory {directory}: {e}")

    return files


async def warm_cache(
    content_cache,
    directory: Path,
    recursive: bool = True,
    pattern: str = '*',
    concurrency: int = 10,
    progress_callback: Optional[callable] = None,
) -> WarmupStats:
    """
    Pre-populate cache with file contents from a directory.

    This function recursively scans a directory, finds text files, and loads
    their content into the cache using controlled concurrency. This improves
    performance for subsequent file operations by avoiding cold cache misses.

    Args:
        content_cache: ContentCache instance to populate
        directory: Directory to scan for files
        recursive: Whether to search recursively (default: True)
        pattern: Glob pattern to match files (default: '*')
        concurrency: Maximum number of concurrent cache operations (default: 10)
        progress_callback: Optional callback function called after each file is processed.
                         Should accept (current: int, total: int, file_path: Path)

    Returns:
        WarmupStats object containing statistics about the warmup operation

    Example:
        >>> from app.cache import ContentCache, PersistentCache, FileStateTracker
        >>> cache = PersistentCache()
        >>> tracker = FileStateTracker(cache)
        >>> content_cache = ContentCache(cache, tracker)
        >>>
        >>> stats = await warm_cache(
        ...     content_cache,
        ...     Path('./data'),
        ...     recursive=True,
        ...     concurrency=10
        ... )
        >>> print(stats)
        Cache Warmup Statistics:
          Files Processed: 150
          Succeeded: 148 (98.7%)
          Failed: 2
          Data Cached: 2.45 MB

    Note:
        - Only text files are cached (see TEXT_EXTENSIONS for supported types)
        - Common directories like node_modules, .git, etc. are automatically skipped
        - Uses asyncio.Semaphore to control concurrency and avoid overwhelming the system
        - Failed files are logged but don't stop the warmup process
    """
    stats = WarmupStats()

    # Find all text files
    logger.info(f"Scanning directory: {directory} (recursive={recursive}, pattern={pattern})")
    files = await find_text_files(directory, recursive=recursive, pattern=pattern)

    if not files:
        logger.warning(f"No text files found in {directory}")
        return stats

    logger.info(f"Found {len(files)} text files to cache")

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)

    async def cache_file(file_path: Path, index: int) -> None:
        """Cache a single file with semaphore control."""
        async with semaphore:
            try:
                # Read file content using asyncio.to_thread for I/O
                content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')

                # Store in cache (this will also update file state)
                await content_cache.get_content(
                    file_path,
                    loader=lambda p: asyncio.to_thread(p.read_text, encoding='utf-8')
                )

                # Track success
                file_size = len(content.encode('utf-8'))
                stats.add_success(file_path, file_size)

                logger.debug(f"Cached: {file_path} ({file_size} bytes)")

            except UnicodeDecodeError as e:
                # File is not actually a text file
                error_msg = f"Not a text file: {e}"
                stats.add_failure(file_path, error_msg)
                logger.debug(f"Skipped: {file_path} ({error_msg})")

            except Exception as e:
                # Other errors (permission denied, file not found, etc.)
                error_msg = str(e)
                stats.add_failure(file_path, error_msg)
                logger.error(f"Failed to cache {file_path}: {error_msg}")

            finally:
                # Report progress
                if progress_callback:
                    await asyncio.to_thread(
                        progress_callback,
                        index + 1,
                        len(files),
                        file_path
                    )

    # Cache all files concurrently
    tasks = [cache_file(file_path, i) for i, file_path in enumerate(files)]
    await asyncio.gather(*tasks)

    logger.info(f"Cache warmup complete: {stats.files_succeeded}/{len(files)} files cached")

    return stats


async def warm_cache_selective(
    content_cache,
    file_paths: list[Path],
    concurrency: int = 10,
    progress_callback: Optional[callable] = None,
) -> WarmupStats:
    """
    Pre-populate cache with specific files.

    Similar to warm_cache() but accepts an explicit list of files instead of
    scanning a directory. Useful for caching a curated set of files.

    Args:
        content_cache: ContentCache instance to populate
        file_paths: List of file paths to cache
        concurrency: Maximum number of concurrent cache operations (default: 10)
        progress_callback: Optional callback function called after each file

    Returns:
        WarmupStats object containing statistics about the warmup operation

    Example:
        >>> files_to_cache = [
        ...     Path('./data/important.txt'),
        ...     Path('./config.yaml'),
        ...     Path('./README.md'),
        ... ]
        >>> stats = await warm_cache_selective(content_cache, files_to_cache)
        >>> print(f"Cached {stats.files_succeeded} files")
    """
    stats = WarmupStats()

    if not file_paths:
        logger.warning("No files provided for selective warmup")
        return stats

    logger.info(f"Warming cache for {len(file_paths)} specific files")

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)

    async def cache_file(file_path: Path, index: int) -> None:
        """Cache a single file with semaphore control."""
        async with semaphore:
            # Skip if not a file
            if not file_path.is_file():
                stats.add_failure(file_path, "Not a file")
                logger.warning(f"Skipped: {file_path} (not a file)")
                return

            try:
                # Read and cache file
                content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')

                await content_cache.get_content(
                    file_path,
                    loader=lambda p: asyncio.to_thread(p.read_text, encoding='utf-8')
                )

                file_size = len(content.encode('utf-8'))
                stats.add_success(file_path, file_size)

                logger.debug(f"Cached: {file_path} ({file_size} bytes)")

            except Exception as e:
                error_msg = str(e)
                stats.add_failure(file_path, error_msg)
                logger.error(f"Failed to cache {file_path}: {error_msg}")

            finally:
                if progress_callback:
                    await asyncio.to_thread(
                        progress_callback,
                        index + 1,
                        len(file_paths),
                        file_path
                    )

    # Cache all files concurrently
    tasks = [cache_file(file_path, i) for i, file_path in enumerate(file_paths)]
    await asyncio.gather(*tasks)

    logger.info(f"Selective cache warmup complete: {stats.files_succeeded}/{len(file_paths)} files cached")

    return stats
