"""
Sandboxed command executor for the Filesystem Agent.
Provides secure execution of whitelisted commands within a confined directory.
"""

import asyncio
import os
import shlex
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# Whitelisted commands that can be executed
# Only POSIX-compliant commands that work on both macOS (BSD) and Linux (GNU)
ALLOWED_COMMANDS = frozenset({
    "grep",   # Search file contents (POSIX)
    "find",   # Find files (POSIX)
    "cat",    # Read files (POSIX)
    "head",   # Read first N lines (POSIX)
    "tail",   # Read last N lines (POSIX)
    "ls",     # List directory (POSIX)
    "wc",     # Word/line count (POSIX)
})

# Default limits
DEFAULT_MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_TIMEOUT = 30  # seconds


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"


class SandboxError(Exception):
    """Base exception for sandbox-related errors."""
    pass


class PathTraversalError(SandboxError):
    """Raised when a path traversal attack is detected."""
    pass


class CommandNotAllowedError(SandboxError):
    """Raised when a command is not in the whitelist."""
    pass


class ExecutionTimeoutError(SandboxError):
    """Raised when command execution times out."""
    pass


class FileTooLargeError(SandboxError):
    """Raised when a file exceeds the maximum allowed size."""

    def __init__(self, file_path: Path, file_size: int, max_size: int):
        self.file_path = file_path
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(
            f"File '{file_path.name}' ({format_size(file_size)}) exceeds "
            f"maximum allowed size ({format_size(max_size)}). "
            f"Use 'head' to read the first N lines instead."
        )


@dataclass
class ExecutionResult:
    """Result of a sandboxed command execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    command: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "command": self.command,
            "error": self.error,
        }


class SandboxExecutor:
    """
    Executes shell commands within a sandboxed environment.

    Security features:
    - Only allows whitelisted commands
    - Confines execution to a specific root directory
    - Prevents path traversal attacks
    - Enforces execution timeouts
    - Limits output size
    - Limits file size for cat operations
    """

    def __init__(
        self,
        root_path: Path,
        timeout: int = DEFAULT_TIMEOUT,
        max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        enabled: bool = True
    ):
        """
        Initialize the sandbox executor.

        Args:
            root_path: The root directory for sandboxed operations
            timeout: Maximum execution time in seconds
            max_output_size: Maximum output size in bytes (default: 1MB)
            max_file_size: Maximum file size for cat operations in bytes (default: 10MB)
            enabled: If False, sandbox checks are bypassed (for testing only)
        """
        self.root_path = root_path.resolve()
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.max_file_size = max_file_size
        self.enabled = enabled

        # Ensure root path exists
        if not self.root_path.exists():
            self.root_path.mkdir(parents=True, exist_ok=True)

    def validate_command(self, command: list[str]) -> None:
        """
        Validate that a command is allowed.

        Args:
            command: The command as a list of strings

        Raises:
            CommandNotAllowedError: If the command is not whitelisted
        """
        if not command:
            raise CommandNotAllowedError("Empty command")

        cmd_name = Path(command[0]).name  # Handle full paths like /usr/bin/grep
        if cmd_name not in ALLOWED_COMMANDS:
            raise CommandNotAllowedError(
                f"Command '{cmd_name}' is not allowed. "
                f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

    def validate_path(self, path: str) -> Path:
        """
        Validate and resolve a path within the sandbox.

        Args:
            path: The path to validate (can be relative or absolute)

        Returns:
            The resolved absolute path

        Raises:
            PathTraversalError: If the path escapes the sandbox
        """
        # Handle relative paths
        if not Path(path).is_absolute():
            resolved = (self.root_path / path).resolve()
        else:
            resolved = Path(path).resolve()

        # Check if the resolved path is within the sandbox
        try:
            resolved.relative_to(self.root_path)
        except ValueError:
            raise PathTraversalError(
                f"Path '{path}' is outside the sandbox root '{self.root_path}'"
            )

        return resolved

    def _looks_like_path(self, arg: str) -> bool:
        """
        Determine if an argument looks like a filesystem path.

        This is conservative to avoid treating grep patterns, numbers,
        glob patterns, or other arguments as paths.
        """
        # Glob patterns are not paths (e.g., *.txt, file?.log)
        if "*" in arg or "?" in arg:
            return False

        # Contains directory separator - likely a path
        if "/" in arg:
            return True

        # Current or parent directory reference
        if arg in (".", ".."):
            return True

        # Has a file extension (e.g., test.txt, README.md)
        if "." in arg and not arg.startswith("."):
            parts = arg.rsplit(".", 1)
            if len(parts) == 2 and len(parts[1]) <= 5 and parts[1].isalnum():
                # Only treat as path if the file actually exists
                potential_path = self.root_path / arg
                if potential_path.exists():
                    return True

        # Check if it exists in the sandbox root (actual file/directory)
        potential_path = self.root_path / arg
        if potential_path.exists():
            return True

        return False

    def _check_file_size_for_cat(self, command: list[str], sanitized: list[str]) -> None:
        """
        Check file sizes for cat commands to prevent reading huge files.

        Args:
            command: Original command
            sanitized: Sanitized command with resolved paths

        Raises:
            FileTooLargeError: If any file exceeds the maximum size
        """
        cmd_name = Path(command[0]).name
        if cmd_name != "cat":
            return

        # Check each file argument
        for arg in sanitized[1:]:
            if arg.startswith("-"):
                continue

            file_path = Path(arg)
            if file_path.is_file():
                file_size = file_path.stat().st_size
                if file_size > self.max_file_size:
                    raise FileTooLargeError(file_path, file_size, self.max_file_size)

    def sanitize_command(self, command: list[str]) -> list[str]:
        """
        Sanitize command arguments by validating paths.

        Args:
            command: The command as a list of strings

        Returns:
            The sanitized command with resolved paths
        """
        if not self.enabled:
            return command

        sanitized = [command[0]]  # Keep the command name

        for arg in command[1:]:
            # Skip flags (arguments starting with -)
            if arg.startswith("-"):
                sanitized.append(arg)
                continue

            # Only validate and resolve if it looks like a path
            if self._looks_like_path(arg):
                try:
                    resolved = self.validate_path(arg)
                    sanitized.append(str(resolved))
                except PathTraversalError:
                    raise
                except Exception:
                    # Validation failed, keep as-is
                    sanitized.append(arg)
            else:
                # Not a path, keep as-is (e.g., grep pattern, numbers)
                sanitized.append(arg)

        return sanitized

    async def execute(self, command: list[str]) -> ExecutionResult:
        """
        Execute a command in the sandbox.

        Args:
            command: The command as a list of strings

        Returns:
            ExecutionResult with the command output
        """
        command_str = shlex.join(command)

        try:
            # Validate command is allowed
            self.validate_command(command)

            # Sanitize paths in command
            sanitized_command = self.sanitize_command(command)
            sanitized_str = shlex.join(sanitized_command)

            # Check file size for cat commands
            self._check_file_size_for_cat(command, sanitized_command)

            # Execute the command
            process = await asyncio.create_subprocess_exec(
                *sanitized_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.root_path),
                env={**os.environ, "LC_ALL": "C.UTF-8"},  # Ensure consistent output
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise ExecutionTimeoutError(
                    f"Command timed out after {self.timeout} seconds"
                )

            # Truncate output if too large
            stdout_str = stdout.decode("utf-8", errors="replace")[:self.max_output_size]
            stderr_str = stderr.decode("utf-8", errors="replace")[:self.max_output_size]

            return ExecutionResult(
                success=process.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode or 0,
                command=sanitized_str,
            )

        except SandboxError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=command_str,
                error=type(e).__name__,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Unexpected error: {str(e)}",
                return_code=-1,
                command=command_str,
                error="UnexpectedError",
            )

    async def execute_from_string(self, command_str: str) -> ExecutionResult:
        """
        Execute a command from a string.

        Args:
            command_str: The command as a string

        Returns:
            ExecutionResult with the command output
        """
        try:
            command = shlex.split(command_str)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Failed to parse command: {str(e)}",
                return_code=-1,
                command=command_str,
                error="ParseError",
            )

        return await self.execute(command)
