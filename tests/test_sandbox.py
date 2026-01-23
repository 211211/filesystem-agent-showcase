"""
Tests for the sandbox executor.
"""

import pytest
from pathlib import Path
import tempfile
import os

from app.sandbox.executor import (
    SandboxExecutor,
    ExecutionResult,
    FileTooLargeError,
)
from app.exceptions import (
    PathTraversalException,
    CommandNotAllowedException,
)


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Resolve to handle macOS symlinks (/var -> /private/var)
        test_dir = Path(tmpdir).resolve()
        (test_dir / "test.txt").write_text("Hello, World!\nLine 2\nLine 3")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("Nested content")
        yield test_dir


@pytest.fixture
def sandbox(temp_data_dir):
    """Create a sandbox executor for testing."""
    return SandboxExecutor(root_path=temp_data_dir, timeout=10, enabled=True)


class TestCommandValidation:
    """Tests for command validation."""

    def test_allowed_command(self, sandbox):
        """Test that allowed commands pass validation."""
        sandbox.validate_command(["ls", "."])
        sandbox.validate_command(["cat", "test.txt"])
        sandbox.validate_command(["grep", "pattern", "."])

    def test_disallowed_command(self, sandbox):
        """Test that disallowed commands raise errors."""
        with pytest.raises(CommandNotAllowedException):
            sandbox.validate_command(["rm", "-rf", "."])

        with pytest.raises(CommandNotAllowedException):
            sandbox.validate_command(["chmod", "+x", "file"])

        with pytest.raises(CommandNotAllowedException):
            sandbox.validate_command(["curl", "http://evil.com"])

    def test_empty_command(self, sandbox):
        """Test that empty commands raise errors."""
        with pytest.raises(CommandNotAllowedException):
            sandbox.validate_command([])


class TestPathValidation:
    """Tests for path validation."""

    def test_valid_relative_path(self, sandbox, temp_data_dir):
        """Test that valid relative paths are accepted."""
        result = sandbox.validate_path("test.txt")
        assert result == temp_data_dir / "test.txt"

    def test_valid_subdirectory_path(self, sandbox, temp_data_dir):
        """Test that subdirectory paths are accepted."""
        result = sandbox.validate_path("subdir/nested.txt")
        assert result == temp_data_dir / "subdir" / "nested.txt"

    def test_path_traversal_blocked(self, sandbox):
        """Test that path traversal attempts are blocked."""
        with pytest.raises(PathTraversalException):
            sandbox.validate_path("../../../etc/passwd")

        with pytest.raises(PathTraversalException):
            sandbox.validate_path("/etc/passwd")


class TestCommandExecution:
    """Tests for command execution."""

    @pytest.mark.asyncio
    async def test_ls_command(self, sandbox, temp_data_dir):
        """Test executing ls command."""
        result = await sandbox.execute(["ls", "."])
        assert result.success
        assert "test.txt" in result.stdout
        assert "subdir" in result.stdout

    @pytest.mark.asyncio
    async def test_cat_command(self, sandbox, temp_data_dir):
        """Test executing cat command."""
        result = await sandbox.execute(["cat", "test.txt"])
        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_grep_command(self, sandbox, temp_data_dir):
        """Test executing grep command."""
        result = await sandbox.execute(["grep", "Hello", "test.txt"])
        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_find_command(self, sandbox, temp_data_dir):
        """Test executing find command."""
        result = await sandbox.execute(["find", ".", "-name", "*.txt"])
        assert result.success
        assert "test.txt" in result.stdout

    @pytest.mark.asyncio
    async def test_head_command(self, sandbox, temp_data_dir):
        """Test executing head command."""
        result = await sandbox.execute(["head", "-n", "1", "test.txt"])
        assert result.success
        assert "Hello, World!" in result.stdout
        assert "Line 2" not in result.stdout

    @pytest.mark.asyncio
    async def test_wc_command(self, sandbox, temp_data_dir):
        """Test executing wc command."""
        result = await sandbox.execute(["wc", "-l", "test.txt"])
        assert result.success
        assert "3" in result.stdout

    @pytest.mark.asyncio
    async def test_disallowed_command_execution(self, sandbox):
        """Test that disallowed commands fail gracefully."""
        result = await sandbox.execute(["rm", "test.txt"])
        assert not result.success
        assert result.error == "COMMAND_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_path_traversal_execution(self, sandbox):
        """Test that path traversal is blocked during execution."""
        result = await sandbox.execute(["cat", "../../../etc/passwd"])
        assert not result.success
        assert result.error == "PATH_TRAVERSAL"

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, sandbox):
        """Test reading a file that doesn't exist."""
        result = await sandbox.execute(["cat", "nonexistent.txt"])
        assert not result.success
        assert result.return_code != 0


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ExecutionResult(
            success=True,
            stdout="output",
            stderr="",
            return_code=0,
            command="ls .",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "output"
        assert d["return_code"] == 0
