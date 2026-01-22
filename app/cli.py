"""
Command-line interface for filesystem-agent-showcase cache management.

This module provides CLI commands for cache operations including:
- warm-cache: Pre-populate cache with file contents
- clear-cache: Clear all caches
- cache-stats: Display cache statistics
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import click

from app.cache import CacheManager, warm_cache
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """
    Filesystem Agent Showcase CLI.

    Command-line tools for cache management and maintenance.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")


@cli.command('warm-cache')
@click.option(
    '--directory', '-d',
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help='Directory to scan and cache files from'
)
@click.option(
    '--recursive', '-r',
    is_flag=True,
    default=True,
    help='Recursively scan subdirectories (default: True)'
)
@click.option(
    '--pattern', '-p',
    default='*',
    help='Glob pattern to match files (default: *)'
)
@click.option(
    '--concurrency', '-c',
    default=10,
    type=click.IntRange(1, 50),
    help='Maximum concurrent cache operations (default: 10)'
)
@click.option(
    '--cache-dir',
    type=str,
    default=None,
    help='Custom cache directory (default: from config)'
)
@click.option(
    '--quiet', '-q',
    is_flag=True,
    help='Suppress progress output'
)
def warm_cache_command(
    directory: Path,
    recursive: bool,
    pattern: str,
    concurrency: int,
    cache_dir: Optional[str],
    quiet: bool,
):
    """
    Pre-populate cache with file contents from a directory.

    This command scans a directory for text files and loads their contents
    into the cache, improving performance for subsequent file operations.

    Examples:

        \b
        # Cache all files in ./data directory
        python -m app.cli warm-cache -d ./data

        \b
        # Cache only Python files
        python -m app.cli warm-cache -d ./src -p "*.py"

        \b
        # Non-recursive caching with custom concurrency
        python -m app.cli warm-cache -d ./config --no-recursive -c 20

        \b
        # Use custom cache directory
        python -m app.cli warm-cache -d ./data --cache-dir /tmp/custom-cache
    """
    async def run_warmup():
        # Initialize cache manager
        if cache_dir:
            cache_manager = CacheManager(cache_dir=cache_dir)
        else:
            settings = get_settings()
            cache_manager = CacheManager.default(settings)

        if not quiet:
            click.echo(f"Starting cache warmup...")
            click.echo(f"  Directory: {directory}")
            click.echo(f"  Recursive: {recursive}")
            click.echo(f"  Pattern: {pattern}")
            click.echo(f"  Concurrency: {concurrency}")
            click.echo(f"  Cache location: {cache_manager.persistent_cache._cache.directory}")
            click.echo()

        # Progress callback
        def progress_callback(current: int, total: int, file_path: Path):
            if not quiet and current % 10 == 0:  # Update every 10 files
                percentage = (current / total) * 100
                click.echo(f"Progress: {current}/{total} ({percentage:.1f}%) - {file_path.name}", err=True)

        try:
            # Warm the cache
            with click.progressbar(
                length=0,
                label='Warming cache',
                show_pos=False,
                show_percent=False
            ) if not quiet else nullcontext():
                stats = await warm_cache(
                    cache_manager.content_cache,
                    directory=directory,
                    recursive=recursive,
                    pattern=pattern,
                    concurrency=concurrency,
                    progress_callback=progress_callback if not quiet else None,
                )

            # Display results
            if not quiet:
                click.echo()
                click.echo(click.style("Cache Warmup Complete!", fg='green', bold=True))
                click.echo()
                click.echo(str(stats))
                click.echo()

                # Show cache stats
                cache_stats = cache_manager.stats()
                disk_stats = cache_stats['disk_cache']
                click.echo("Current Cache Statistics:")
                click.echo(f"  Total entries: {disk_stats['size']}")
                click.echo(f"  Disk usage: {disk_stats['volume'] / (1024 * 1024):.2f} MB")
                click.echo(f"  Cache directory: {disk_stats['directory']}")

            # Check if there were errors
            if stats.files_failed > 0:
                click.echo()
                click.echo(click.style(
                    f"Warning: {stats.files_failed} files failed to cache. See logs for details.",
                    fg='yellow'
                ), err=True)
                return 1  # Exit code 1 for partial failure

            return 0

        except Exception as e:
            click.echo(click.style(f"Error during cache warmup: {e}", fg='red'), err=True)
            logger.exception("Cache warmup failed")
            return 1

        finally:
            cache_manager.close()

    # Run the async function
    exit_code = asyncio.run(run_warmup())
    raise SystemExit(exit_code)


@cli.command('clear-cache')
@click.option(
    '--cache-dir',
    type=str,
    default=None,
    help='Custom cache directory (default: from config)'
)
@click.option(
    '--force', '-f',
    is_flag=True,
    help='Skip confirmation prompt'
)
def clear_cache_command(cache_dir: Optional[str], force: bool):
    """
    Clear all caches and remove all cached data.

    This operation is irreversible and will permanently remove all cached
    file contents, search results, and file state tracking data.

    Examples:

        \b
        # Clear cache with confirmation
        python -m app.cli clear-cache

        \b
        # Clear cache without confirmation
        python -m app.cli clear-cache --force

        \b
        # Clear custom cache directory
        python -m app.cli clear-cache --cache-dir /tmp/custom-cache -f
    """
    async def run_clear():
        # Initialize cache manager
        if cache_dir:
            cache_manager = CacheManager(cache_dir=cache_dir)
        else:
            settings = get_settings()
            cache_manager = CacheManager.default(settings)

        # Get current stats before clearing
        stats = cache_manager.stats()
        disk_stats = stats['disk_cache']

        click.echo("Current Cache Statistics:")
        click.echo(f"  Total entries: {disk_stats['size']}")
        click.echo(f"  Disk usage: {disk_stats['volume'] / (1024 * 1024):.2f} MB")
        click.echo(f"  Cache directory: {disk_stats['directory']}")
        click.echo()

        # Confirm unless --force is used
        if not force:
            if not click.confirm("Are you sure you want to clear ALL cache data?"):
                click.echo("Operation cancelled.")
                cache_manager.close()
                return 0

        try:
            # Clear the cache
            await cache_manager.clear_all()

            click.echo(click.style("Cache cleared successfully!", fg='green', bold=True))

            # Verify cache is empty
            new_stats = cache_manager.stats()
            new_disk_stats = new_stats['disk_cache']
            click.echo(f"Current entries: {new_disk_stats['size']}")

            return 0

        except Exception as e:
            click.echo(click.style(f"Error clearing cache: {e}", fg='red'), err=True)
            logger.exception("Cache clear failed")
            return 1

        finally:
            cache_manager.close()

    # Run the async function
    exit_code = asyncio.run(run_clear())
    raise SystemExit(exit_code)


@cli.command('cache-stats')
@click.option(
    '--cache-dir',
    type=str,
    default=None,
    help='Custom cache directory (default: from config)'
)
@click.option(
    '--json',
    'output_json',
    is_flag=True,
    help='Output statistics as JSON'
)
def cache_stats_command(cache_dir: Optional[str], output_json: bool):
    """
    Display comprehensive cache statistics.

    Shows information about cache size, disk usage, configuration,
    and performance metrics.

    Examples:

        \b
        # Display cache statistics
        python -m app.cli cache-stats

        \b
        # Output as JSON
        python -m app.cli cache-stats --json

        \b
        # Check custom cache directory
        python -m app.cli cache-stats --cache-dir /tmp/custom-cache
    """
    try:
        # Initialize cache manager
        if cache_dir:
            cache_manager = CacheManager(cache_dir=cache_dir)
        else:
            settings = get_settings()
            cache_manager = CacheManager.default(settings)

        # Get cache statistics
        stats = cache_manager.stats()

        if output_json:
            # Output as JSON
            import json
            click.echo(json.dumps(stats, indent=2))
        else:
            # Output as formatted text
            disk_stats = stats['disk_cache']
            config = stats['configuration']

            click.echo(click.style("Cache Statistics", fg='blue', bold=True))
            click.echo()

            click.echo("Storage:")
            click.echo(f"  Total entries: {disk_stats['size']}")
            click.echo(f"  Disk usage: {disk_stats['volume'] / (1024 * 1024):.2f} MB")
            click.echo(f"  Cache directory: {disk_stats['directory']}")
            click.echo()

            click.echo("Configuration:")
            click.echo(f"  Size limit: {config.get('size_limit', 'unknown')} bytes")
            if isinstance(config.get('size_limit'), int):
                click.echo(f"             ({config['size_limit'] / (1024 * 1024):.2f} MB)")
            click.echo(f"  Eviction policy: {config['eviction_policy']}")
            click.echo(f"  Content TTL: {stats['content_ttl']} seconds")
            click.echo(f"  Search TTL: {stats['search_ttl']} seconds")
            click.echo()

            # Calculate usage percentage if size limit is known
            size_limit = config.get('size_limit')
            if isinstance(size_limit, int) and size_limit > 0:
                usage_pct = (disk_stats['volume'] / size_limit) * 100
                click.echo(f"Cache Usage: {usage_pct:.1f}%")

                # Add colored bar
                bar_width = 40
                filled = int(bar_width * usage_pct / 100)
                bar = '█' * filled + '░' * (bar_width - filled)

                if usage_pct < 50:
                    color = 'green'
                elif usage_pct < 80:
                    color = 'yellow'
                else:
                    color = 'red'

                click.echo(click.style(bar, fg=color))

        cache_manager.close()
        return 0

    except Exception as e:
        click.echo(click.style(f"Error getting cache stats: {e}", fg='red'), err=True)
        logger.exception("Failed to get cache stats")
        return 1


# Context manager helper for when progressbar is not used
class nullcontext:
    """Null context manager for conditional context usage."""
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


if __name__ == '__main__':
    cli()
