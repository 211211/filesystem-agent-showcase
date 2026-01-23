"""Tool Registry for managing tool definitions and command building.

This module provides a registry pattern for tool definitions, allowing dynamic
registration, lookup, and command building for bash tools used by the agent.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional, Any


@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


@dataclass
class ToolDefinition:
    """Complete tool definition"""
    name: str
    description: str
    parameters: List[ToolParameter]
    builder: Callable[[dict], List[str]]
    cacheable: bool = True
    cache_ttl: Optional[int] = None

    def to_openai_format(self) -> dict:
        """Convert to OpenAI function calling format"""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


class ToolRegistry:
    """Registry to manage tool definitions"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_all(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        """List all tool names"""
        return list(self._tools.keys())

    def to_openai_format(self) -> List[dict]:
        """Convert all tools to OpenAI format"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    def build_command(self, name: str, arguments: dict) -> List[str]:
        """Build command for a tool"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        # Filter empty strings from command
        cmd = tool.builder(arguments)
        return [arg for arg in cmd if arg]

    def is_cacheable(self, name: str) -> bool:
        """Check if tool results should be cached"""
        tool = self.get(name)
        return tool.cacheable if tool else False

    def get_cache_ttl(self, name: str) -> Optional[int]:
        """Get cache TTL for tool"""
        tool = self.get(name)
        return tool.cache_ttl if tool else None

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_default_registry() -> ToolRegistry:
    """Create registry with default bash tools"""
    registry = ToolRegistry()

    # grep tool
    registry.register(ToolDefinition(
        name="grep",
        description="Search for a pattern in files using grep",
        parameters=[
            ToolParameter("pattern", "string", "The regex pattern to search for"),
            ToolParameter("path", "string", "File or directory path to search"),
            ToolParameter("recursive", "boolean", "Search recursively in directories", False, True),
            ToolParameter("ignore_case", "boolean", "Case insensitive search", False, False),
            ToolParameter("line_number", "boolean", "Show line numbers", False, True),
        ],
        builder=lambda args: [
            "grep",
            "-n" if args.get("line_number", True) else "",
            "-r" if args.get("recursive", True) else "",
            "-i" if args.get("ignore_case", False) else "",
            args["pattern"],
            args["path"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    # find tool
    registry.register(ToolDefinition(
        name="find",
        description="Find files by name pattern",
        parameters=[
            ToolParameter("path", "string", "Directory to search in"),
            ToolParameter("name", "string", "File name pattern (supports wildcards)"),
            ToolParameter("type", "string", "File type: f (file), d (directory)", False, "f"),
        ],
        builder=lambda args: [
            "find",
            args["path"],
            "-type", args.get("type", "f"),
            "-name", args["name"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    # cat tool
    registry.register(ToolDefinition(
        name="cat",
        description="Display entire file contents",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
        ],
        builder=lambda args: ["cat", args["path"]],
        cacheable=True,
        cache_ttl=0  # Invalidate on file change only
    ))

    # head tool
    registry.register(ToolDefinition(
        name="head",
        description="Display first N lines of a file",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
            ToolParameter("lines", "integer", "Number of lines to show", False, 10),
        ],
        builder=lambda args: ["head", "-n", str(args.get("lines", 10)), args["path"]],
        cacheable=True,
        cache_ttl=0
    ))

    # tail tool
    registry.register(ToolDefinition(
        name="tail",
        description="Display last N lines of a file",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
            ToolParameter("lines", "integer", "Number of lines to show", False, 10),
        ],
        builder=lambda args: ["tail", "-n", str(args.get("lines", 10)), args["path"]],
        cacheable=True,
        cache_ttl=0
    ))

    # ls tool
    registry.register(ToolDefinition(
        name="ls",
        description="List directory contents",
        parameters=[
            ToolParameter("path", "string", "Directory path to list"),
            ToolParameter("all", "boolean", "Show hidden files", False, False),
            ToolParameter("long", "boolean", "Use long format", False, False),
        ],
        builder=lambda args: [
            "ls",
            "-a" if args.get("all", False) else "",
            "-l" if args.get("long", False) else "",
            args["path"]
        ],
        cacheable=False,  # Directory listing changes frequently
        cache_ttl=None
    ))

    # wc tool
    registry.register(ToolDefinition(
        name="wc",
        description="Count lines, words, and characters in a file",
        parameters=[
            ToolParameter("path", "string", "File path to count"),
            ToolParameter("lines", "boolean", "Count lines only", False, False),
            ToolParameter("words", "boolean", "Count words only", False, False),
        ],
        builder=lambda args: [
            "wc",
            "-l" if args.get("lines", False) else "",
            "-w" if args.get("words", False) else "",
            args["path"]
        ],
        cacheable=False,
        cache_ttl=None
    ))

    return registry
