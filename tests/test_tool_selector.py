"""
Tests for the tool selector module.
"""

from app.agent.tools.tool_selector import ToolSelector
from app.agent.tools.bash_tools import BASH_TOOLS


class TestToolSelectorIntentDetection:
    """Tests for intent detection."""

    def test_detect_search_intent(self):
        """Should detect search intent."""
        intents = ToolSelector.detect_intent("find all python files")
        assert "search" in intents

    def test_detect_search_intent_with_locate(self):
        """Should detect search intent with locate keyword."""
        intents = ToolSelector.detect_intent("locate the config file")
        assert "search" in intents

    def test_detect_search_intent_with_where(self):
        """Should detect search intent with where keyword."""
        intents = ToolSelector.detect_intent("where is the readme?")
        assert "search" in intents

    def test_detect_read_intent(self):
        """Should detect read intent."""
        intents = ToolSelector.detect_intent("show me the content of config.py")
        assert "read" in intents

    def test_detect_read_intent_with_view(self):
        """Should detect read intent with view keyword."""
        intents = ToolSelector.detect_intent("view the file")
        assert "read" in intents

    def test_detect_read_intent_with_whats_in(self):
        """Should detect read intent with what's in phrase."""
        intents = ToolSelector.detect_intent("what's in this file?")
        assert "read" in intents

    def test_detect_analyze_intent(self):
        """Should detect analyze intent."""
        intents = ToolSelector.detect_intent("count the number of lines")
        assert "analyze" in intents

    def test_detect_analyze_intent_with_how_many(self):
        """Should detect analyze intent with how many phrase."""
        intents = ToolSelector.detect_intent("how many files are there?")
        assert "analyze" in intents

    def test_detect_analyze_intent_with_statistics(self):
        """Should detect analyze intent with statistics keyword."""
        intents = ToolSelector.detect_intent("show me statistics about the code")
        assert "analyze" in intents

    def test_detect_list_intent(self):
        """Should detect list intent."""
        intents = ToolSelector.detect_intent("list all files in directory")
        assert "list" in intents

    def test_detect_list_intent_with_ls(self):
        """Should detect list intent with ls keyword."""
        intents = ToolSelector.detect_intent("ls the current folder")
        assert "list" in intents

    def test_detect_list_intent_with_folder(self):
        """Should detect list intent with folder keyword."""
        intents = ToolSelector.detect_intent("what's in this folder?")
        assert "list" in intents

    def test_detect_pattern_intent(self):
        """Should detect pattern intent."""
        intents = ToolSelector.detect_intent("grep for TODO comments")
        assert "pattern" in intents

    def test_detect_pattern_intent_with_match(self):
        """Should detect pattern intent with match keyword."""
        intents = ToolSelector.detect_intent("match all lines with error")
        assert "pattern" in intents

    def test_detect_pattern_intent_with_contain(self):
        """Should detect pattern intent with contain keyword."""
        intents = ToolSelector.detect_intent("files that contain import")
        assert "pattern" in intents

    def test_detect_multiple_intents(self):
        """Should detect multiple intents."""
        intents = ToolSelector.detect_intent("find and read all config files")
        assert "search" in intents
        assert "read" in intents

    def test_detect_three_intents(self):
        """Should detect three intents at once."""
        intents = ToolSelector.detect_intent("find files, read content, and count lines")
        assert "search" in intents
        assert "read" in intents
        assert "analyze" in intents

    def test_no_intent_detected(self):
        """Empty intents for unclear message."""
        intents = ToolSelector.detect_intent("hello world")
        assert len(intents) == 0

    def test_no_intent_for_greeting(self):
        """Empty intents for greeting."""
        intents = ToolSelector.detect_intent("hi there, how are you?")
        assert len(intents) == 0

    def test_english_search_with_locate(self):
        """Should support English search keywords with locate."""
        intents = ToolSelector.detect_intent("locate all config files")
        assert "search" in intents

    def test_english_read_with_display(self):
        """Should support English read keywords with display."""
        intents = ToolSelector.detect_intent("display file content")
        assert "read" in intents

    def test_english_analyze_with_stats(self):
        """Should support English analyze keywords with count."""
        intents = ToolSelector.detect_intent("count number of lines")
        assert "analyze" in intents

    def test_case_insensitive_detection(self):
        """Intent detection should be case insensitive."""
        intents1 = ToolSelector.detect_intent("FIND all files")
        intents2 = ToolSelector.detect_intent("Find all files")
        intents3 = ToolSelector.detect_intent("find all files")
        assert "search" in intents1
        assert "search" in intents2
        assert "search" in intents3


class TestToolSelectorToolSelection:
    """Tests for tool selection."""

    def test_search_intent_returns_search_tools(self):
        """Search intent should include find, grep, ls."""
        tools = ToolSelector.select_tools("find all python files", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names
        assert "grep" in tool_names
        assert "ls" in tool_names

    def test_read_intent_returns_read_tools(self):
        """Read intent should include cat, head."""
        tools = ToolSelector.select_tools("show me the file content", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "head" in tool_names
        # cat or smart_read should be present
        assert "cat" in tool_names or "smart_read" in tool_names

    def test_analyze_intent_returns_analyze_tools(self):
        """Analyze intent should include wc, grep."""
        tools = ToolSelector.select_tools("count the lines", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "wc" in tool_names
        assert "grep" in tool_names

    def test_list_intent_returns_list_tools(self):
        """List intent should include ls, tree, find."""
        tools = ToolSelector.select_tools("list directory contents", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "ls" in tool_names
        assert "tree" in tool_names
        assert "find" in tool_names

    def test_pattern_intent_returns_pattern_tools(self):
        """Pattern intent should include grep, find."""
        tools = ToolSelector.select_tools("grep for errors", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "grep" in tool_names
        assert "find" in tool_names

    def test_unknown_intent_returns_all_tools(self):
        """Unknown intent with include_all_on_unknown=True should return all."""
        tools = ToolSelector.select_tools("hello", include_all_on_unknown=True)
        assert len(tools) == len(BASH_TOOLS)

    def test_unknown_intent_returns_essential_only(self):
        """Unknown intent with include_all_on_unknown=False should return essentials."""
        tools = ToolSelector.select_tools("hello", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "ls" in tool_names
        assert "head" in tool_names

    def test_essential_tools_always_included(self):
        """Essential tools should always be included."""
        tools = ToolSelector.select_tools("find python files", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        # Essential tools: ls, head
        assert "ls" in tool_names
        assert "head" in tool_names

    def test_previous_tools_included(self):
        """Previously used tools should be included."""
        tools = ToolSelector.select_tools(
            "find files",
            previous_tools={"cat", "wc"},
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "cat" in tool_names
        assert "wc" in tool_names

    def test_previous_tools_with_empty_set(self):
        """Empty previous tools should not affect selection."""
        tools_without = ToolSelector.select_tools("find files", include_all_on_unknown=False)
        tools_with_empty = ToolSelector.select_tools("find files", previous_tools=set(), include_all_on_unknown=False)

        assert len(tools_without) == len(tools_with_empty)

    def test_previous_tools_with_none(self):
        """None previous tools should not affect selection."""
        tools_without = ToolSelector.select_tools("find files", include_all_on_unknown=False)
        tools_with_none = ToolSelector.select_tools("find files", previous_tools=None, include_all_on_unknown=False)

        assert len(tools_without) == len(tools_with_none)

    def test_tool_count_reduction(self):
        """Should reduce tool count for specific intents."""
        selected, total = ToolSelector.get_tool_count_reduction("find python files")

        assert selected < total
        assert total == len(BASH_TOOLS)

    def test_tool_count_reduction_for_read(self):
        """Should reduce tool count for read intent."""
        selected, total = ToolSelector.get_tool_count_reduction("read the config file")

        assert selected < total
        assert selected >= 2  # At least essential tools

    def test_no_reduction_for_unknown(self):
        """No reduction for unknown intent when include_all_on_unknown=True."""
        tools = ToolSelector.select_tools("hello there", include_all_on_unknown=True)
        assert len(tools) == len(BASH_TOOLS)


class TestToolSelectorIntegration:
    """Integration tests for tool selection."""

    def test_returns_valid_tool_definitions(self):
        """Selected tools should be valid OpenAI tool definitions."""
        tools = ToolSelector.select_tools("find and read config")

        for tool in tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "parameters" in tool["function"]

    def test_all_selected_tools_exist_in_bash_tools(self):
        """All selected tool names should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}

        for message in ["find files", "read content", "count lines", "list directory"]:
            tools = ToolSelector.select_tools(message, include_all_on_unknown=False)
            for tool in tools:
                assert tool["function"]["name"] in all_tool_names

    def test_tool_definitions_match_bash_tools(self):
        """Selected tool definitions should match original BASH_TOOLS definitions."""
        tools = ToolSelector.select_tools("find files", include_all_on_unknown=False)

        # Find the 'find' tool in selected tools
        find_tool = next((t for t in tools if t["function"]["name"] == "find"), None)
        assert find_tool is not None

        # Find the 'find' tool in BASH_TOOLS
        original_find_tool = next((t for t in BASH_TOOLS if t["function"]["name"] == "find"), None)
        assert original_find_tool is not None

        # They should be identical
        assert find_tool == original_find_tool

    def test_combined_intents_include_all_relevant_tools(self):
        """Combined intents should include tools from all detected intents."""
        tools = ToolSelector.select_tools(
            "find all python files, read their content, and count lines",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should include search tools
        assert "find" in tool_names
        # Should include read tools
        assert "cat" in tool_names or "head" in tool_names
        # Should include analyze tools
        assert "wc" in tool_names

    def test_real_world_query_file_exploration(self):
        """Test real-world query for file exploration."""
        tools = ToolSelector.select_tools(
            "What files are in the src directory?",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should detect list intent
        assert "ls" in tool_names
        # May also include find
        assert "find" in tool_names or "tree" in tool_names

    def test_real_world_query_content_search(self):
        """Test real-world query for content search."""
        tools = ToolSelector.select_tools(
            "Search for TODO comments in all Python files",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should detect search intent
        assert "grep" in tool_names or "find" in tool_names

    def test_real_world_query_file_reading(self):
        """Test real-world query for file reading."""
        tools = ToolSelector.select_tools(
            "Show me the contents of README.md",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        # Should detect read intent
        assert "cat" in tool_names or "head" in tool_names


class TestToolSelectorEdgeCases:
    """Edge case tests for tool selection."""

    def test_empty_message(self):
        """Empty message should return all tools with include_all_on_unknown=True."""
        tools = ToolSelector.select_tools("", include_all_on_unknown=True)
        assert len(tools) == len(BASH_TOOLS)

    def test_empty_message_with_include_all_false(self):
        """Empty message with include_all_on_unknown=False should return essentials."""
        tools = ToolSelector.select_tools("", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        # Should have essential tools
        assert "ls" in tool_names
        assert "head" in tool_names

    def test_whitespace_only_message(self):
        """Whitespace-only message should return all tools with include_all_on_unknown=True."""
        tools = ToolSelector.select_tools("   \t\n  ", include_all_on_unknown=True)
        assert len(tools) == len(BASH_TOOLS)

    def test_special_characters_in_message(self):
        """Special characters should not break intent detection."""
        tools = ToolSelector.select_tools("find files with @#$%^&*()", include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names

    def test_very_long_message(self):
        """Very long message should still work."""
        long_message = "find " + "a " * 1000 + "files"
        tools = ToolSelector.select_tools(long_message, include_all_on_unknown=False)
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names

    def test_multiple_keyword_occurrences(self):
        """Multiple occurrences of same keyword should still work."""
        tools = ToolSelector.select_tools(
            "find find find find all python files",
            include_all_on_unknown=False
        )
        tool_names = {t["function"]["name"] for t in tools}

        assert "find" in tool_names


class TestToolSelectorClassAttributes:
    """Tests for class attributes and constants."""

    def test_all_tool_names_matches_bash_tools(self):
        """ALL_TOOL_NAMES should match BASH_TOOLS."""
        expected_names = {t["function"]["name"] for t in BASH_TOOLS}
        assert ToolSelector.ALL_TOOL_NAMES == expected_names

    def test_essential_tools_exist_in_bash_tools(self):
        """Essential tools should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        for essential in ToolSelector.ESSENTIAL_TOOLS:
            assert essential in all_tool_names

    def test_search_tools_exist_in_bash_tools(self):
        """Search tools should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        for tool in ToolSelector.SEARCH_TOOLS:
            assert tool in all_tool_names

    def test_read_tools_exist_in_bash_tools(self):
        """Read tools should exist in BASH_TOOLS or be optional."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        # At least some read tools should exist
        existing_read_tools = ToolSelector.READ_TOOLS.intersection(all_tool_names)
        assert len(existing_read_tools) >= 1

    def test_analyze_tools_exist_in_bash_tools(self):
        """Analyze tools should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        for tool in ToolSelector.ANALYZE_TOOLS:
            assert tool in all_tool_names

    def test_list_tools_exist_in_bash_tools(self):
        """List tools should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        for tool in ToolSelector.LIST_TOOLS:
            assert tool in all_tool_names

    def test_pattern_tools_exist_in_bash_tools(self):
        """Pattern tools should exist in BASH_TOOLS."""
        all_tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        for tool in ToolSelector.PATTERN_TOOLS:
            assert tool in all_tool_names
