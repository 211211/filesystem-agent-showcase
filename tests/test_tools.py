"""
Tests for the bash tools module.
"""

import pytest
from app.agent.tools.bash_tools import (
    BASH_TOOLS,
    build_command,
    build_grep_command,
    build_find_command,
    build_cat_command,
    build_head_command,
    build_ls_command,
    build_tree_command,
    build_wc_command,
)


class TestBashToolDefinitions:
    """Tests for bash tool definitions."""

    def test_all_tools_have_required_fields(self):
        """Test that all tool definitions have required fields."""
        for tool in BASH_TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool

            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_expected_tools_exist(self):
        """Test that all expected tools are defined."""
        tool_names = {t["function"]["name"] for t in BASH_TOOLS}
        expected = {"grep", "find", "cat", "head", "ls", "tree", "wc"}
        assert expected.issubset(tool_names)


class TestBuildGrepCommand:
    """Tests for grep command building."""

    def test_basic_grep(self):
        """Test basic grep command."""
        cmd = build_grep_command("pattern", "path")
        assert cmd == ["grep", "-n", "-r", "pattern", "path"]

    def test_grep_non_recursive(self):
        """Test non-recursive grep."""
        cmd = build_grep_command("pattern", "path", recursive=False)
        assert cmd == ["grep", "-n", "pattern", "path"]

    def test_grep_case_insensitive(self):
        """Test case-insensitive grep."""
        cmd = build_grep_command("pattern", "path", ignore_case=True)
        assert "-i" in cmd


class TestBuildFindCommand:
    """Tests for find command building."""

    def test_basic_find(self):
        """Test basic find command."""
        cmd = build_find_command(".", "*.md")
        assert cmd == ["find", ".", "-type", "f", "-name", "*.md"]

    def test_find_directories(self):
        """Test finding directories."""
        cmd = build_find_command(".", "*", file_type="d")
        assert "-type" in cmd
        assert "d" in cmd


class TestBuildCatCommand:
    """Tests for cat command building (Head-First pattern)."""

    def test_basic_cat(self):
        """Test basic cat command uses head -n 100 by default (Head-First pattern)."""
        cmd = build_cat_command("file.txt")
        assert cmd == ["head", "-n", "100", "file.txt"]

    def test_cat_full_reads_entire_file(self):
        """Test cat with full=True reads entire file."""
        cmd = build_cat_command("file.txt", full=True)
        assert cmd == ["cat", "file.txt"]


class TestBuildHeadCommand:
    """Tests for head command building."""

    def test_basic_head(self):
        """Test basic head command."""
        cmd = build_head_command("file.txt")
        assert cmd == ["head", "-n", "10", "file.txt"]

    def test_head_custom_lines(self):
        """Test head with custom line count."""
        cmd = build_head_command("file.txt", lines=5)
        assert cmd == ["head", "-n", "5", "file.txt"]


class TestBuildLsCommand:
    """Tests for ls command building."""

    def test_basic_ls(self):
        """Test basic ls command."""
        cmd = build_ls_command(".")
        assert cmd == ["ls", "."]

    def test_ls_all(self):
        """Test ls with -a flag."""
        cmd = build_ls_command(".", show_all=True)
        assert "-a" in cmd

    def test_ls_long(self):
        """Test ls with -l flag."""
        cmd = build_ls_command(".", long_format=True)
        assert "-l" in cmd


class TestBuildTreeCommand:
    """Tests for tree command building (uses find internally)."""

    def test_basic_tree(self):
        """Test basic tree command uses find."""
        cmd = build_tree_command(".")
        assert cmd == ["find", ".", "-maxdepth", "3", "-print"]

    def test_tree_custom_depth(self):
        """Test tree with custom depth."""
        cmd = build_tree_command(".", max_depth=5)
        assert "find" in cmd
        assert "-maxdepth" in cmd
        assert "5" in cmd


class TestBuildWcCommand:
    """Tests for wc command building."""

    def test_basic_wc(self):
        """Test basic wc command."""
        cmd = build_wc_command("file.txt")
        assert cmd == ["wc", "file.txt"]

    def test_wc_lines_only(self):
        """Test wc with lines only."""
        cmd = build_wc_command("file.txt", lines_only=True)
        assert "-l" in cmd


class TestBuildCommand:
    """Tests for the unified build_command function."""

    def test_build_grep_from_args(self):
        """Test building grep from argument dict."""
        args = {"pattern": "TODO", "path": ".", "recursive": True}
        cmd = build_command("grep", args)
        assert "grep" in cmd[0]
        assert "TODO" in cmd
        assert "." in cmd

    def test_build_find_from_args(self):
        """Test building find from argument dict."""
        args = {"path": ".", "name_pattern": "*.py"}
        cmd = build_command("find", args)
        assert "find" in cmd[0]
        assert "*.py" in cmd

    def test_build_cat_from_args(self):
        """Test building cat from argument dict uses head -n 100 by default."""
        args = {"path": "readme.md"}
        cmd = build_command("cat", args)
        assert cmd == ["head", "-n", "100", "readme.md"]

    def test_build_cat_full_from_args(self):
        """Test building cat with full=True reads entire file."""
        args = {"path": "readme.md", "full": True}
        cmd = build_command("cat", args)
        assert cmd == ["cat", "readme.md"]

    def test_invalid_tool_raises_error(self):
        """Test that invalid tool name raises ValueError."""
        with pytest.raises(ValueError):
            build_command("invalid_tool", {})
