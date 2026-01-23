"""
Tool Handlers using Chain of Responsibility pattern.

This module demonstrates the Chain of Responsibility design pattern for handling
different types of tool calls. Each handler in the chain decides whether it can
handle a specific tool call or passes it to the next handler.

The chain is built as:
CachedReadHandler -> CachedSearchHandler -> DefaultHandler

This allows for:
- Separation of concerns (each handler handles one type of tool)
- Easy extensibility (add new handlers without modifying existing ones)
- Clear delegation flow (handlers explicitly pass to next in chain)
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.agent.filesystem_agent import ToolCall
from app.cache import CacheManager
from app.sandbox.executor import SandboxExecutor, ExecutionResult

logger = logging.getLogger(__name__)


class ToolHandler(ABC):
    """
    Abstract base class for tool handlers in the Chain of Responsibility pattern.

    Each handler can either:
    1. Handle the tool call if it recognizes the tool type
    2. Pass the tool call to the next handler in the chain
    """

    def __init__(self, next_handler: Optional["ToolHandler"] = None):
        """
        Initialize the handler.

        Args:
            next_handler: The next handler in the chain, or None if this is the last handler
        """
        self._next_handler = next_handler

    async def handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
        """
        Handle a tool call or delegate to the next handler.

        This method implements the chain logic: if this handler can handle the tool,
        it does so. Otherwise, it delegates to the next handler in the chain.

        Args:
            tool_call: The tool call to handle
            **kwargs: Additional context (e.g., sandbox, cache_manager, data_root)

        Returns:
            ExecutionResult from executing the tool

        Raises:
            ValueError: If no handler in the chain can handle the tool
        """
        if self.can_handle(tool_call):
            logger.debug(f"{self.__class__.__name__} handling tool: {tool_call.name}")
            return await self._do_handle(tool_call, **kwargs)
        elif self._next_handler:
            logger.debug(f"{self.__class__.__name__} passing to next handler: {tool_call.name}")
            return await self._next_handler.handle(tool_call, **kwargs)
        else:
            raise ValueError(f"No handler found for tool: {tool_call.name}")

    @abstractmethod
    def can_handle(self, tool_call: ToolCall) -> bool:
        """
        Determine if this handler can handle the given tool call.

        Args:
            tool_call: The tool call to check

        Returns:
            True if this handler can handle the tool call, False otherwise
        """
        pass

    @abstractmethod
    async def _do_handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
        """
        Actually handle the tool call.

        This method is called only when can_handle() returns True.

        Args:
            tool_call: The tool call to execute
            **kwargs: Additional context needed for execution

        Returns:
            ExecutionResult from executing the tool
        """
        pass


class CachedReadHandler(ToolHandler):
    """
    Handles file read operations (cat, head, tail) with ContentCache.

    This handler uses the CacheManager's ContentCache to cache full file contents,
    avoiding repeated disk reads. For operations like head/tail, the full content
    is cached and then sliced per request.
    """

    def can_handle(self, tool_call: ToolCall) -> bool:
        """Check if this is a file read operation."""
        return tool_call.name in ["cat", "head", "tail"]

    async def _do_handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
        """
        Execute a cached file read operation.

        Expected kwargs:
            - cache_manager: CacheManager instance
            - sandbox: SandboxExecutor instance
            - data_root: Path to data root directory
        """
        cache_manager: CacheManager = kwargs.get("cache_manager")
        sandbox: SandboxExecutor = kwargs.get("sandbox")
        data_root: Path = kwargs.get("data_root")

        if not cache_manager:
            raise ValueError("CachedReadHandler requires cache_manager in kwargs")
        if not sandbox:
            raise ValueError("CachedReadHandler requires sandbox in kwargs")
        if not data_root:
            raise ValueError("CachedReadHandler requires data_root in kwargs")

        path_str = tool_call.arguments.get("path", "")
        file_path = (data_root / path_str).resolve()

        try:
            # Define the loader function that reads FULL file content
            async def load_full_file(p: Path) -> str:
                from app.agent.tools.bash_tools import build_cat_command
                command = build_cat_command(path_str)
                result = await sandbox.execute(command)
                if result.success:
                    return result.stdout
                else:
                    raise Exception(f"Failed to read file: {result.stderr}")

            # Get FULL content from cache
            full_content = await cache_manager.content_cache.get_content(
                file_path,
                load_full_file
            )

            # Apply operation-specific processing AFTER cache retrieval
            if tool_call.name == "head":
                content = self._process_head(full_content, tool_call.arguments)
            elif tool_call.name == "tail":
                content = self._process_tail(full_content, tool_call.arguments)
            else:
                # cat - return full content
                content = full_content

            # Build command string for logging
            # Note: tail is not in BASH_TOOLS, so we build it manually
            if tool_call.name == "tail":
                command = ["tail", "-n", str(tool_call.arguments.get("lines", 10)), path_str]
            else:
                from app.agent.tools.bash_tools import build_command
                command = build_command(tool_call.name, tool_call.arguments)

            return ExecutionResult(
                success=True,
                stdout=content,
                stderr="",
                return_code=0,
                command=" ".join(command) if isinstance(command, list) else str(command),
                error=None,
            )

        except Exception as e:
            logger.error(f"Error in cached read for {tool_call.name}: {e}")
            # Build command for error logging
            if tool_call.name == "tail":
                command = ["tail", "-n", str(tool_call.arguments.get("lines", 10)), path_str]
            else:
                from app.agent.tools.bash_tools import build_command
                command = build_command(tool_call.name, tool_call.arguments)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=" ".join(command) if isinstance(command, list) else str(command),
                error="CachedReadError",
            )

    def _process_head(self, full_content: str, arguments: dict) -> str:
        """Process head operation on full content."""
        lines = arguments.get("lines", 10)
        content_lines = full_content.split("\n")
        sliced_lines = content_lines[:lines]
        content = "\n".join(sliced_lines)

        # Add trailing newline if original had one
        if full_content and full_content.endswith("\n") and content and not content.endswith("\n"):
            content += "\n"

        return content

    def _process_tail(self, full_content: str, arguments: dict) -> str:
        """Process tail operation on full content."""
        lines = arguments.get("lines", 10)
        content_lines = full_content.split("\n")

        # Handle trailing newline
        if content_lines and content_lines[-1] == "" and full_content.endswith("\n"):
            content_lines = content_lines[:-1]
            sliced_lines = content_lines[-lines:]
            content = "\n".join(sliced_lines)
            if content:
                content += "\n"
        else:
            sliced_lines = content_lines[-lines:]
            content = "\n".join(sliced_lines)

        return content


class CachedSearchHandler(ToolHandler):
    """
    Handles search operations (grep, find) with SearchCache.

    This handler uses the CacheManager's SearchCache to cache search results,
    with automatic invalidation when files change.
    """

    def can_handle(self, tool_call: ToolCall) -> bool:
        """Check if this is a search operation."""
        return tool_call.name in ["grep", "find"]

    async def _do_handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
        """
        Execute a cached search operation.

        Expected kwargs:
            - cache_manager: CacheManager instance
            - sandbox: SandboxExecutor instance
            - data_root: Path to data root directory
        """
        cache_manager: CacheManager = kwargs.get("cache_manager")
        sandbox: SandboxExecutor = kwargs.get("sandbox")
        data_root: Path = kwargs.get("data_root")

        if not cache_manager:
            raise ValueError("CachedSearchHandler requires cache_manager in kwargs")
        if not sandbox:
            raise ValueError("CachedSearchHandler requires sandbox in kwargs")
        if not data_root:
            raise ValueError("CachedSearchHandler requires data_root in kwargs")

        try:
            # Build the command
            from app.agent.tools.bash_tools import build_command
            command = build_command(tool_call.name, tool_call.arguments)

            # Define the search function
            async def execute_search() -> ExecutionResult:
                return await sandbox.execute(command)

            # Get search scope (path from arguments)
            path_str = tool_call.arguments.get("path", ".")
            scope_path = (data_root / path_str).resolve()

            # Get result from cache
            result = await cache_manager.search_cache.get_search(
                tool_call.name,
                tool_call.arguments,
                scope_path,
                execute_search
            )

            return result

        except Exception as e:
            logger.error(f"Error in cached search for {tool_call.name}: {e}")
            from app.agent.tools.bash_tools import build_command
            command = build_command(tool_call.name, tool_call.arguments)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=" ".join(command) if isinstance(command, list) else str(command),
                error="CachedSearchError",
            )


class DefaultHandler(ToolHandler):
    """
    Default handler that executes tools directly through the sandbox.

    This handler catches all tools that aren't handled by specialized handlers
    (e.g., ls, tree, wc, smart_read). It always returns True for can_handle(),
    making it the catch-all at the end of the chain.
    """

    def can_handle(self, tool_call: ToolCall) -> bool:
        """This handler can handle any tool call (catch-all)."""
        return True

    async def _do_handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
        """
        Execute the tool directly through the sandbox.

        Expected kwargs:
            - sandbox: SandboxExecutor instance
        """
        sandbox: SandboxExecutor = kwargs.get("sandbox")

        if not sandbox:
            raise ValueError("DefaultHandler requires sandbox in kwargs")

        try:
            from app.agent.tools.bash_tools import build_command
            command = build_command(tool_call.name, tool_call.arguments)

            # Handle smart_read specially (it returns dict, not list)
            if tool_call.name == "smart_read":
                # For now, just return an error - smart_read needs special handling
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr="smart_read not supported by handler chain yet",
                    return_code=-1,
                    command=f"smart_read {tool_call.arguments}",
                    error="NotImplemented",
                )

            result = await sandbox.execute(command)
            return result

        except Exception as e:
            logger.error(f"Error executing {tool_call.name}: {e}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=f"{tool_call.name} {tool_call.arguments}",
                error="ExecutionError",
            )


def create_handler_chain(
    cache_manager: Optional[CacheManager] = None,
) -> ToolHandler:
    """
    Create the tool handler chain.

    The chain is built as:
    CachedReadHandler -> CachedSearchHandler -> DefaultHandler

    If cache_manager is provided, cached handlers will use it.
    If cache_manager is None, all tools will fall through to DefaultHandler.

    Args:
        cache_manager: Optional CacheManager for cached handlers

    Returns:
        The first handler in the chain
    """
    # Build chain from end to beginning
    default_handler = DefaultHandler()

    if cache_manager:
        # With cache: CachedReadHandler -> CachedSearchHandler -> DefaultHandler
        search_handler = CachedSearchHandler(next_handler=default_handler)
        read_handler = CachedReadHandler(next_handler=search_handler)
        return read_handler
    else:
        # Without cache: DefaultHandler only
        return default_handler
