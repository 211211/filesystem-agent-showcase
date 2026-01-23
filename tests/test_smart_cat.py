import pytest
from app.agent.tools.bash_tools import build_smart_cat_command, build_command, BASH_TOOLS


class TestSmartCatTool:
    def test_smart_cat_in_bash_tools(self):
        """smart_cat should be in BASH_TOOLS."""
        tool_names = [t["function"]["name"] for t in BASH_TOOLS]
        assert "smart_cat" in tool_names

    def test_smart_cat_default_mode_is_head(self):
        """Default mode should be head."""
        cmd = build_smart_cat_command(path="test.txt")
        assert cmd == ["head", "-n", "100", "test.txt"]

    def test_smart_cat_head_mode(self):
        """Head mode with custom lines."""
        cmd = build_smart_cat_command(path="test.txt", mode="head", lines=50)
        assert cmd == ["head", "-n", "50", "test.txt"]

    def test_smart_cat_tail_mode(self):
        """Tail mode should use tail command."""
        cmd = build_smart_cat_command(path="test.txt", mode="tail", lines=20)
        assert cmd == ["tail", "-n", "20", "test.txt"]

    def test_smart_cat_range_mode(self):
        """Range mode should use sed."""
        cmd = build_smart_cat_command(path="test.txt", mode="range", start_line=10, end_line=20)
        assert cmd == ["sed", "-n", "10,20p", "test.txt"]

    def test_smart_cat_range_mode_defaults(self):
        """Range mode should have sensible defaults."""
        cmd = build_smart_cat_command(path="test.txt", mode="range")
        assert cmd == ["sed", "-n", "1,101p", "test.txt"]

    def test_smart_cat_full_mode(self):
        """Full mode should use cat."""
        cmd = build_smart_cat_command(path="test.txt", mode="full")
        assert cmd == ["cat", "test.txt"]

    def test_build_command_smart_cat(self):
        """build_command should work with smart_cat."""
        cmd = build_command("smart_cat", {"path": "test.txt", "mode": "tail", "lines": 15})
        assert cmd == ["tail", "-n", "15", "test.txt"]

    def test_build_command_smart_cat_range(self):
        """build_command should work with smart_cat range mode."""
        cmd = build_command("smart_cat", {"path": "test.txt", "mode": "range", "start_line": 5, "end_line": 10})
        assert cmd == ["sed", "-n", "5,10p", "test.txt"]


class TestSedInAllowedCommands:
    def test_sed_in_allowed_commands(self):
        """sed should be in allowed commands for range mode."""
        from app.sandbox.executor import ALLOWED_COMMANDS
        assert "sed" in ALLOWED_COMMANDS
