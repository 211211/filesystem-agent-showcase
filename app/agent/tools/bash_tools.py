"""
Bash tools for the Filesystem Agent.
Provides wrappers around common Unix commands for file exploration.
"""

from typing import Any, Callable, Optional

# Tool definitions for OpenAI function calling format
BASH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a pattern in files. Returns matching lines with file names and line numbers. Use for finding specific content within files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory path to search in (relative to data root)"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Search recursively in subdirectories",
                        "default": True
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case-insensitive search",
                        "default": False
                    }
                },
                "required": ["pattern", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": "Find files by name pattern. Returns list of matching file paths. Use for locating files with specific names or extensions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (relative to data root)"
                    },
                    "name_pattern": {
                        "type": "string",
                        "description": "File name pattern (supports wildcards like *.md, *.py)"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["f", "d"],
                        "description": "Type: 'f' for files, 'd' for directories",
                        "default": "f"
                    }
                },
                "required": ["path", "name_pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cat",
            "description": "Read ENTIRE file contents. WARNING: Expensive for large files. Use 'preview' first to see beginning, then 'cat' only if you need complete content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative to data root)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "head",
            "description": "Read the first N lines of a file. Use for previewing file content or reading large files partially.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file (relative to data root)"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to read from the beginning",
                        "default": 10
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview",
            "description": "Preview the beginning of a file. PREFERRED tool for reading files. Returns first 100 lines with metadata (total lines, size). Use this before deciding to read full file with 'cat'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Lines to preview (default: 100, max: 500)",
                        "default": 100
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ls",
            "description": "List directory contents. Returns files and subdirectories with details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (relative to data root)"
                    },
                    "all": {
                        "type": "boolean",
                        "description": "Include hidden files (starting with .)",
                        "default": False
                    },
                    "long": {
                        "type": "boolean",
                        "description": "Show detailed information (size, permissions, date)",
                        "default": False
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tree",
            "description": "List all files and directories recursively up to a certain depth. Use to understand the organization of files and folders in a directory structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Root directory path (relative to data root)"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse",
                        "default": 3
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wc",
            "description": "Count lines, words, and characters in files. Use for getting statistics about file content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file or directory (relative to data root)"
                    },
                    "lines_only": {
                        "type": "boolean",
                        "description": "Only count lines",
                        "default": False
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "smart_read",
            "description": "Intelligently read a file based on its size. For small files (<1MB), reads the entire content. For medium files (1-100MB) with a query, uses grep. For large files (>100MB), reads head and tail portions. Use this for reading files of unknown size safely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read (relative to data root)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search pattern for grep strategy (used for medium-sized files)"
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum lines to read from head/tail for large files",
                        "default": 100
                    }
                },
                "required": ["path"]
            }
        }
    }
]


def build_grep_command(
    pattern: str,
    path: str,
    recursive: bool = True,
    ignore_case: bool = False
) -> list[str]:
    """Build grep command arguments."""
    cmd = ["grep", "-n"]  # -n for line numbers
    if recursive:
        cmd.append("-r")
    if ignore_case:
        cmd.append("-i")
    cmd.extend([pattern, path])
    return cmd


def build_find_command(
    path: str,
    name_pattern: str,
    file_type: str = "f"
) -> list[str]:
    """Build find command arguments."""
    cmd = ["find", path, "-type", file_type, "-name", name_pattern]
    return cmd


def build_cat_command(path: str) -> list[str]:
    """Build cat command arguments."""
    return ["cat", path]


def build_head_command(path: str, lines: int = 10) -> list[str]:
    """Build head command arguments."""
    return ["head", "-n", str(lines), path]


def build_preview_command(path: str, lines: int = 100) -> list[str]:
    """Build preview command (head with line limit)."""
    return ["head", "-n", str(min(lines, 500)), path]


def build_ls_command(
    path: str,
    show_all: bool = False,
    long_format: bool = False
) -> list[str]:
    """Build ls command arguments."""
    cmd = ["ls"]
    if show_all:
        cmd.append("-a")
    if long_format:
        cmd.append("-l")
    cmd.append(path)
    return cmd


def build_tree_command(path: str, max_depth: int = 3) -> list[str]:
    """
    Build tree command arguments.
    Uses 'find' as it's universally available (tree may not be installed).
    """
    # Use find to list files with depth limit - works on all Unix systems
    return ["find", path, "-maxdepth", str(max_depth), "-print"]


def build_wc_command(path: str, lines_only: bool = False) -> list[str]:
    """Build wc command arguments."""
    cmd = ["wc"]
    if lines_only:
        cmd.append("-l")
    cmd.append(path)
    return cmd


def build_smart_read_command(
    path: str,
    query: Optional[str] = None,
    max_lines: int = 100
) -> dict:
    """
    Build smart_read command arguments.

    Note: This returns a dict with parameters for AdaptiveFileReader,
    not a shell command list, since smart_read uses the AdaptiveFileReader class.

    Args:
        path: Path to the file
        query: Optional search query
        max_lines: Maximum lines for head/tail strategy

    Returns:
        Dictionary with parameters for AdaptiveFileReader.smart_read()
    """
    return {
        "path": path,
        "query": query,
        "max_lines": max_lines
    }


def get_command_builder(tool_name: str) -> Optional[Callable[..., Any]]:
    """Get the command builder function for a tool."""
    builders = {
        "grep": build_grep_command,
        "find": build_find_command,
        "cat": build_cat_command,
        "head": build_head_command,
        "preview": build_preview_command,
        "ls": build_ls_command,
        "tree": build_tree_command,
        "wc": build_wc_command,
        "smart_read": build_smart_read_command,
    }
    return builders.get(tool_name)


def build_command(tool_name: str, args: dict[str, Any]) -> list[str]:
    """Build a command from tool name and arguments."""
    builder = get_command_builder(tool_name)
    if not builder:
        raise ValueError(f"Unknown tool: {tool_name}")

    # Map argument names to builder parameter names
    arg_mapping = {
        "grep": lambda a: build_grep_command(
            pattern=a["pattern"],
            path=a["path"],
            recursive=a.get("recursive", True),
            ignore_case=a.get("ignore_case", False)
        ),
        "find": lambda a: build_find_command(
            path=a["path"],
            name_pattern=a["name_pattern"],
            file_type=a.get("type", "f")
        ),
        "cat": lambda a: build_cat_command(path=a["path"]),
        "head": lambda a: build_head_command(
            path=a["path"],
            lines=a.get("lines", 10)
        ),
        "preview": lambda a: build_preview_command(
            path=a["path"],
            lines=min(a.get("lines", 100), 500)
        ),
        "ls": lambda a: build_ls_command(
            path=a["path"],
            show_all=a.get("all", False),
            long_format=a.get("long", False)
        ),
        "tree": lambda a: build_tree_command(
            path=a["path"],
            max_depth=a.get("max_depth", 3)
        ),
        "wc": lambda a: build_wc_command(
            path=a["path"],
            lines_only=a.get("lines_only", False)
        ),
        "smart_read": lambda a: build_smart_read_command(
            path=a["path"],
            query=a.get("query"),
            max_lines=a.get("max_lines", 100)
        ),
    }

    return arg_mapping[tool_name](args)
