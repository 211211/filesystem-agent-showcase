"""
Tests for cache warmup functionality.
"""

import asyncio
from pathlib import Path
import pytest
import tempfile

from app.cache import CacheManager, warm_cache, warm_cache_selective, WarmupStats
from app.cache.warmup import is_text_file, should_skip, find_text_files


class TestTextFileDetection:
    """Tests for text file detection."""

    def test_is_text_file_python(self):
        """Test detection of Python files."""
        assert is_text_file(Path("test.py")) is True
        assert is_text_file(Path("module.py")) is True

    def test_is_text_file_javascript(self):
        """Test detection of JavaScript files."""
        assert is_text_file(Path("app.js")) is True
        assert is_text_file(Path("component.jsx")) is True
        assert is_text_file(Path("component.tsx")) is True

    def test_is_text_file_markdown(self):
        """Test detection of Markdown files."""
        assert is_text_file(Path("README.md")) is True
        assert is_text_file(Path("docs.markdown")) is True

    def test_is_text_file_config(self):
        """Test detection of config files."""
        assert is_text_file(Path("config.yaml")) is True
        assert is_text_file(Path("config.yml")) is True
        assert is_text_file(Path("package.json")) is True
        assert is_text_file(Path(".env")) is True

    def test_is_text_file_makefile(self):
        """Test detection of Makefile."""
        assert is_text_file(Path("Makefile")) is True
        assert is_text_file(Path("Dockerfile")) is True

    def test_is_not_text_file(self):
        """Test detection of non-text files."""
        assert is_text_file(Path("image.png")) is False
        assert is_text_file(Path("video.mp4")) is False
        assert is_text_file(Path("archive.zip")) is False
        assert is_text_file(Path("binary.exe")) is False


class TestSkipPatterns:
    """Tests for skip pattern detection."""

    def test_should_skip_node_modules(self):
        """Test skipping node_modules."""
        assert should_skip(Path("project/node_modules/package/file.js")) is True

    def test_should_skip_git(self):
        """Test skipping .git directory."""
        assert should_skip(Path("project/.git/config")) is True

    def test_should_skip_pycache(self):
        """Test skipping __pycache__."""
        assert should_skip(Path("project/__pycache__/module.pyc")) is True

    def test_should_not_skip_regular(self):
        """Test not skipping regular files."""
        assert should_skip(Path("project/src/main.py")) is False
        assert should_skip(Path("project/docs/README.md")) is False


class TestWarmupStats:
    """Tests for WarmupStats class."""

    def test_stats_initialization(self):
        """Test stats initialization."""
        stats = WarmupStats()
        assert stats.files_processed == 0
        assert stats.files_succeeded == 0
        assert stats.files_failed == 0
        assert stats.bytes_cached == 0

    def test_add_success(self):
        """Test adding successful cache operation."""
        stats = WarmupStats()
        stats.add_success(Path("test.py"), 1024)

        assert stats.files_processed == 1
        assert stats.files_succeeded == 1
        assert stats.files_failed == 0
        assert stats.bytes_cached == 1024
        assert stats.file_types[".py"] == 1

    def test_add_failure(self):
        """Test adding failed cache operation."""
        stats = WarmupStats()
        stats.add_failure(Path("test.py"), "Permission denied")

        assert stats.files_processed == 1
        assert stats.files_succeeded == 0
        assert stats.files_failed == 1
        assert len(stats.errors) == 1

    def test_to_dict(self):
        """Test converting stats to dictionary."""
        stats = WarmupStats()
        stats.add_success(Path("test.py"), 1024)
        stats.add_failure(Path("test2.py"), "Error")

        result = stats.to_dict()
        assert result['files_processed'] == 2
        assert result['files_succeeded'] == 1
        assert result['files_failed'] == 1
        assert result['bytes_cached'] == 1024
        assert result['errors_count'] == 1

    def test_str_representation(self):
        """Test string representation of stats."""
        stats = WarmupStats()
        stats.add_success(Path("test.py"), 1024)

        result = str(stats)
        assert "Files Processed: 1" in result
        assert "Succeeded: 1" in result


@pytest.mark.asyncio
async def test_find_text_files():
    """Test finding text files in directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        (tmp_path / "test.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Test")
        (tmp_path / "config.json").write_text('{"key": "value"}')
        (tmp_path / "image.png").write_text("not really an image")

        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# nested")

        # Find files recursively
        files = await find_text_files(tmp_path, recursive=True)

        # Should find text files, not image
        file_names = {f.name for f in files}
        assert "test.py" in file_names
        assert "README.md" in file_names
        assert "config.json" in file_names
        assert "nested.py" in file_names
        assert "image.png" not in file_names


@pytest.mark.asyncio
async def test_warm_cache():
    """Test cache warming functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        (tmp_path / "file3.py").write_text("print('test')")

        # Create subdirectory with file
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.md").write_text("# Nested")

        # Create cache manager
        cache_dir = tmp_path / "cache"
        cache_manager = CacheManager(cache_dir=str(cache_dir))

        # Warm the cache
        stats = await warm_cache(
            cache_manager.content_cache,
            tmp_path,
            recursive=True,
            concurrency=2
        )

        # Verify stats
        assert stats.files_processed == 4
        assert stats.files_succeeded == 4
        assert stats.files_failed == 0
        assert stats.bytes_cached > 0

        # Verify files are cached
        content = await cache_manager.content_cache.get_content(
            tmp_path / "file1.txt",
            loader=lambda p: asyncio.to_thread(p.read_text)
        )
        assert content == "Content 1"

        cache_manager.close()


@pytest.mark.asyncio
async def test_warm_cache_selective():
    """Test selective cache warming."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create test files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")

        # Create cache manager
        cache_dir = tmp_path / "cache"
        cache_manager = CacheManager(cache_dir=str(cache_dir))

        # Warm cache with specific files
        stats = await warm_cache_selective(
            cache_manager.content_cache,
            [file1, file2]
        )

        # Verify stats
        assert stats.files_processed == 2
        assert stats.files_succeeded == 2
        assert stats.files_failed == 0

        cache_manager.close()


@pytest.mark.asyncio
async def test_warm_cache_with_pattern():
    """Test cache warming with glob pattern."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create various files
        (tmp_path / "test.py").write_text("python code")
        (tmp_path / "test.js").write_text("javascript code")
        (tmp_path / "README.md").write_text("readme")

        # Create cache manager
        cache_dir = tmp_path / "cache"
        cache_manager = CacheManager(cache_dir=str(cache_dir))

        # Warm cache with pattern (only .py files)
        stats = await warm_cache(
            cache_manager.content_cache,
            tmp_path,
            recursive=False,
            pattern="*.py",
            concurrency=2
        )

        # Should only find .py file
        assert stats.files_processed == 1
        assert stats.files_succeeded == 1

        cache_manager.close()


@pytest.mark.asyncio
async def test_warm_cache_handles_errors():
    """Test cache warming handles errors gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create a file
        good_file = tmp_path / "good.txt"
        good_file.write_text("Good content")

        # Create cache manager
        cache_dir = tmp_path / "cache"
        cache_manager = CacheManager(cache_dir=str(cache_dir))

        # Add a non-existent file to the list
        files = [
            good_file,
            tmp_path / "nonexistent.txt"
        ]

        stats = await warm_cache_selective(
            cache_manager.content_cache,
            files
        )

        # Should have 1 success and 1 failure
        assert stats.files_processed == 2
        assert stats.files_succeeded == 1
        assert stats.files_failed == 1
        assert len(stats.errors) == 1

        cache_manager.close()
