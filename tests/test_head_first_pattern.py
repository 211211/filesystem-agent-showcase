"""Tests for the Head-First pattern in the cat tool."""

import pytest
from app.agent.tools.bash_tools import build_cat_command, build_command


class TestHeadFirstPattern:
    """Test suite for the Head-First pattern implementation."""

    def test_cat_default_uses_head_100_lines(self):
        """Default cat should use head -n 100."""
        cmd = build_cat_command(path="test.txt")
        assert cmd == ["head", "-n", "100", "test.txt"]

    def test_cat_with_custom_lines(self):
        """Cat with custom lines count."""
        cmd = build_cat_command(path="test.txt", lines=50)
        assert cmd == ["head", "-n", "50", "test.txt"]

    def test_cat_full_flag_reads_entire_file(self):
        """Full flag should use actual cat."""
        cmd = build_cat_command(path="test.txt", full=True)
        assert cmd == ["cat", "test.txt"]

    def test_cat_full_flag_ignores_lines(self):
        """Full flag ignores lines parameter."""
        cmd = build_cat_command(path="test.txt", full=True, lines=50)
        assert cmd == ["cat", "test.txt"]

    def test_build_command_cat_default(self):
        """build_command for cat uses head by default."""
        cmd = build_command("cat", {"path": "test.txt"})
        assert cmd == ["head", "-n", "100", "test.txt"]

    def test_build_command_cat_with_lines(self):
        """build_command for cat respects lines parameter."""
        cmd = build_command("cat", {"path": "test.txt", "lines": 25})
        assert cmd == ["head", "-n", "25", "test.txt"]

    def test_build_command_cat_full(self):
        """build_command for cat respects full parameter."""
        cmd = build_command("cat", {"path": "test.txt", "full": True})
        assert cmd == ["cat", "test.txt"]

    def test_cat_with_zero_lines(self):
        """Cat with zero lines should still work."""
        cmd = build_cat_command(path="test.txt", lines=0)
        assert cmd == ["head", "-n", "0", "test.txt"]

    def test_cat_with_large_lines(self):
        """Cat with large lines count."""
        cmd = build_cat_command(path="test.txt", lines=10000)
        assert cmd == ["head", "-n", "10000", "test.txt"]

    def test_cat_backward_compatibility(self):
        """Ensure backward compatibility - cat without params should work."""
        # Old code calling cat with just path should get head -n 100
        cmd = build_command("cat", {"path": "some/file.py"})
        assert cmd[0] == "head"
        assert "-n" in cmd
        assert "100" in cmd
        assert "some/file.py" in cmd
