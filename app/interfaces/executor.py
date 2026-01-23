"""
Executor interface for sandboxed command execution.

This module defines the IExecutor interface that abstracts command execution,
enabling different implementations for production, testing, and alternative
execution environments (e.g., Docker, Kubernetes).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.sandbox.executor import ExecutionResult


class IExecutor(ABC):
    """
    Abstract interface for command execution.

    This interface defines the contract for executing shell commands
    in a controlled environment. Implementations may provide sandboxing,
    caching, or other execution strategies.

    Implementations:
        - SandboxExecutor: Production implementation with security features
        - CachedSandboxExecutor: Executor with result caching (legacy v2.0)

    Example:
        ```python
        class MockExecutor(IExecutor):
            @property
            def root_path(self) -> Path:
                return Path("/tmp/mock")

            @property
            def timeout(self) -> int:
                return 30

            async def execute(self, command: List[str]) -> ExecutionResult:
                return ExecutionResult(
                    success=True,
                    stdout="mocked output",
                    stderr="",
                    return_code=0,
                    command=" ".join(command),
                )

            async def execute_from_string(self, command_str: str) -> ExecutionResult:
                return await self.execute(command_str.split())

            def validate_command(self, command: List[str]) -> None:
                pass  # Accept all commands in mock

            def validate_path(self, path: str) -> Path:
                return self.root_path / path
        ```
    """

    @property
    @abstractmethod
    def root_path(self) -> Path:
        """
        Get the root path for command execution.

        All file operations should be confined within this directory.

        Returns:
            The root directory path for sandboxed operations
        """
        pass

    @property
    @abstractmethod
    def timeout(self) -> int:
        """
        Get the execution timeout in seconds.

        Commands that exceed this timeout will be terminated.

        Returns:
            Timeout duration in seconds
        """
        pass

    @abstractmethod
    async def execute(self, command: List[str]) -> "ExecutionResult":
        """
        Execute a command and return the result.

        This is the primary method for executing commands. Implementations
        should validate commands, sanitize paths, and enforce security policies.

        Args:
            command: The command as a list of strings (e.g., ["grep", "-r", "pattern", "."])

        Returns:
            ExecutionResult containing:
                - success: Whether the command succeeded
                - stdout: Standard output from the command
                - stderr: Standard error from the command
                - return_code: Process exit code
                - command: The executed command string
                - error: Error code if execution failed

        Example:
            >>> result = await executor.execute(["ls", "-la", "/data"])
            >>> if result.success:
            ...     print(result.stdout)
            ... else:
            ...     print(f"Error: {result.stderr}")
        """
        pass

    @abstractmethod
    async def execute_from_string(self, command_str: str) -> "ExecutionResult":
        """
        Execute a command from a string.

        Parses the command string and delegates to execute().

        Args:
            command_str: The command as a single string (e.g., "grep -r pattern .")

        Returns:
            ExecutionResult with the command output

        Raises:
            May return ExecutionResult with error if command string cannot be parsed
        """
        pass

    @abstractmethod
    def validate_command(self, command: List[str]) -> None:
        """
        Validate that a command is allowed.

        Args:
            command: The command to validate

        Raises:
            CommandNotAllowedException: If the command is not whitelisted
            ValueError: If the command is empty or invalid
        """
        pass

    @abstractmethod
    def validate_path(self, path: str) -> Path:
        """
        Validate and resolve a path within the execution context.

        Args:
            path: The path to validate (can be relative or absolute)

        Returns:
            The resolved absolute path within the sandbox

        Raises:
            PathTraversalException: If the path escapes the sandbox boundary
        """
        pass
