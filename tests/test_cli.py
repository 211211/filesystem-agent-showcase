"""
Tests for CLI functionality.
"""

import pytest
from click.testing import CliRunner

from app.cli import cli, warm_cache_command, clear_cache_command, cache_stats_command


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_help(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'Filesystem Agent Showcase CLI' in result.output
        assert 'warm-cache' in result.output
        assert 'clear-cache' in result.output
        assert 'cache-stats' in result.output

    def test_warm_cache_help(self):
        """Test warm-cache command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['warm-cache', '--help'])

        assert result.exit_code == 0
        assert 'Pre-populate cache with file contents' in result.output
        assert '--directory' in result.output
        assert '--recursive' in result.output
        assert '--pattern' in result.output
        assert '--concurrency' in result.output

    def test_clear_cache_help(self):
        """Test clear-cache command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['clear-cache', '--help'])

        assert result.exit_code == 0
        assert 'Clear all caches' in result.output
        assert '--force' in result.output

    def test_cache_stats_help(self):
        """Test cache-stats command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['cache-stats', '--help'])

        assert result.exit_code == 0
        assert 'Display comprehensive cache statistics' in result.output
        assert '--json' in result.output

    def test_warm_cache_requires_directory(self):
        """Test warm-cache command requires directory argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ['warm-cache'])

        assert result.exit_code != 0
        assert 'Missing option' in result.output or 'required' in result.output.lower()

    def test_verbose_flag(self):
        """Test global verbose flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--verbose', '--help'])

        assert result.exit_code == 0
