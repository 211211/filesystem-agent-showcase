"""Tool selector for lazy loading based on user intent."""

from typing import Set
from .bash_tools import BASH_TOOLS


class ToolSelector:
    """Select relevant tools based on user message intent."""

    # Intent keywords mapping
    SEARCH_KEYWORDS = {
        "find", "search", "locate", "where", "look for", "looking for"
    }
    READ_KEYWORDS = {
        "read", "show", "display", "content", "view", "open", "see",
        "cat", "print", "output", "what's in", "what is in"
    }
    ANALYZE_KEYWORDS = {
        "count", "how many", "number of", "statistics", "analyze", "stats"
    }
    LIST_KEYWORDS = {
        "list", "ls", "directory", "folder", "files in", "directories"
    }
    PATTERN_KEYWORDS = {
        "grep", "pattern", "match", "contain", "includes", "has", "matching"
    }

    # Tool groups by category
    SEARCH_TOOLS = {"find", "grep", "ls"}
    READ_TOOLS = {"cat", "head", "tail", "smart_read"}
    ANALYZE_TOOLS = {"wc", "grep"}
    LIST_TOOLS = {"ls", "tree", "find"}
    PATTERN_TOOLS = {"grep", "find"}

    # Essential tools always included
    ESSENTIAL_TOOLS = {"ls", "head"}

    # All tool names in BASH_TOOLS
    ALL_TOOL_NAMES = {t["function"]["name"] for t in BASH_TOOLS}

    @classmethod
    def detect_intent(cls, message: str) -> Set[str]:
        """Detect user intent from message.

        Args:
            message: User message

        Returns:
            Set of intent categories
        """
        message_lower = message.lower()
        intents = set()

        if any(kw in message_lower for kw in cls.SEARCH_KEYWORDS):
            intents.add("search")
        if any(kw in message_lower for kw in cls.READ_KEYWORDS):
            intents.add("read")
        if any(kw in message_lower for kw in cls.ANALYZE_KEYWORDS):
            intents.add("analyze")
        if any(kw in message_lower for kw in cls.LIST_KEYWORDS):
            intents.add("list")
        if any(kw in message_lower for kw in cls.PATTERN_KEYWORDS):
            intents.add("pattern")

        return intents

    @classmethod
    def get_tools_for_intents(cls, intents: Set[str]) -> Set[str]:
        """Get tool names for given intents.

        Args:
            intents: Set of intent categories

        Returns:
            Set of tool names
        """
        tools = set(cls.ESSENTIAL_TOOLS)

        intent_mapping = {
            "search": cls.SEARCH_TOOLS,
            "read": cls.READ_TOOLS,
            "analyze": cls.ANALYZE_TOOLS,
            "list": cls.LIST_TOOLS,
            "pattern": cls.PATTERN_TOOLS,
        }

        for intent in intents:
            if intent in intent_mapping:
                tools.update(intent_mapping[intent])

        return tools

    @classmethod
    def select_tools(
        cls,
        user_message: str,
        previous_tools: Set[str] | None = None,
        include_all_on_unknown: bool = True
    ) -> list[dict]:
        """Select relevant tools based on user intent.

        Args:
            user_message: User's message
            previous_tools: Tools used in previous turns (to include for continuity)
            include_all_on_unknown: If True, return all tools when no intent detected

        Returns:
            List of tool definitions (subset of BASH_TOOLS)
        """
        intents = cls.detect_intent(user_message)

        # If no intent detected, optionally return all tools
        if not intents and include_all_on_unknown:
            return list(BASH_TOOLS)

        # Get tools for detected intents
        selected_names = cls.get_tools_for_intents(intents)

        # Add previously used tools for continuity
        if previous_tools:
            selected_names.update(previous_tools)

        # Filter BASH_TOOLS to only selected
        selected_tools = [
            tool for tool in BASH_TOOLS
            if tool["function"]["name"] in selected_names
        ]

        # Ensure we return at least essential tools
        if not selected_tools:
            return [
                tool for tool in BASH_TOOLS
                if tool["function"]["name"] in cls.ESSENTIAL_TOOLS
            ]

        return selected_tools

    @classmethod
    def get_tool_count_reduction(cls, user_message: str) -> tuple[int, int]:
        """Calculate potential tool count reduction.

        Args:
            user_message: User's message

        Returns:
            Tuple of (selected_count, total_count)
        """
        selected = cls.select_tools(user_message, include_all_on_unknown=False)
        return len(selected), len(BASH_TOOLS)
