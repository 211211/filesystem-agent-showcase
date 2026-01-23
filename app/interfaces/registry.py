"""
Tool registry interface for managing tool definitions.

This module defines the IToolRegistry interface that abstracts
tool definition management, enabling different implementations
for various tool sources (in-memory, file-based, database-based).
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.repositories.tool_registry import ToolDefinition


class IToolRegistry(ABC):
    """
    Abstract interface for tool registries.

    Implementations manage tool definitions, providing registration,
    lookup, and command building functionality for bash tools used
    by the agent.

    Implementations:
        - ToolRegistry: In-memory implementation with default bash tools

    Example:
        ```python
        class FileBasedRegistry(IToolRegistry):
            def __init__(self, config_path: Path):
                self._config_path = config_path
                self._tools = self._load_from_file()

            def register(self, tool: ToolDefinition) -> None:
                self._tools[tool.name] = tool
                self._save_to_file()

            def get(self, name: str) -> Optional[ToolDefinition]:
                return self._tools.get(name)

            def to_openai_format(self) -> List[dict]:
                return [t.to_openai_format() for t in self._tools.values()]

            def build_command(self, name: str, arguments: dict) -> List[str]:
                tool = self.get(name)
                if not tool:
                    raise ValueError(f"Unknown tool: {name}")
                return tool.builder(arguments)

            def is_cacheable(self, name: str) -> bool:
                tool = self.get(name)
                return tool.cacheable if tool else False

            def get_cache_ttl(self, name: str) -> Optional[int]:
                tool = self.get(name)
                return tool.cache_ttl if tool else None
        ```
    """

    @abstractmethod
    def register(self, tool: "ToolDefinition") -> None:
        """
        Register a tool definition.

        Args:
            tool: The tool definition to register

        Note:
            If a tool with the same name exists, it will be overwritten.
        """
        pass

    @abstractmethod
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.

        Args:
            name: The tool name to unregister

        Returns:
            True if the tool was found and unregistered, False if not found
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Optional["ToolDefinition"]:
        """
        Get a tool definition by name.

        Args:
            name: The tool name

        Returns:
            The tool definition if found, None otherwise
        """
        pass

    @abstractmethod
    def list_all(self) -> List["ToolDefinition"]:
        """
        List all registered tool definitions.

        Returns:
            List of all tool definitions
        """
        pass

    @abstractmethod
    def list_names(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        pass

    @abstractmethod
    def to_openai_format(self) -> List[dict]:
        """
        Convert all tools to OpenAI function calling format.

        Returns:
            List of tool definitions in OpenAI format, ready for
            use with the OpenAI API's function calling feature
        """
        pass

    @abstractmethod
    def build_command(self, name: str, arguments: dict) -> List[str]:
        """
        Build command for a tool.

        Args:
            name: Tool name
            arguments: Tool arguments dictionary

        Returns:
            Command as list of strings (e.g., ["grep", "-r", "pattern", "."])

        Raises:
            ValueError: If tool is not found
        """
        pass

    @abstractmethod
    def is_cacheable(self, name: str) -> bool:
        """
        Check if tool results should be cached.

        Args:
            name: Tool name

        Returns:
            True if the tool's results are cacheable, False otherwise
        """
        pass

    @abstractmethod
    def get_cache_ttl(self, name: str) -> Optional[int]:
        """
        Get cache TTL for a tool.

        Args:
            name: Tool name

        Returns:
            TTL in seconds, or None if no specific TTL is configured
        """
        pass
