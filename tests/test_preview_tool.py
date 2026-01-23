"""Tests for the preview tool implementation."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.agent.tools.bash_tools import (
    build_preview_command,
    build_command,
    BASH_TOOLS,
)
from app.agent.filesystem_agent import FilesystemAgent, ToolCall
from app.sandbox.executor import ExecutionResult
from app.repositories.tool_registry import create_default_registry


class TestPreviewCommand:
    """Tests for the preview command builder."""

    def test_build_preview_command_default_lines(self):
        """Test preview command with default line count (100)."""
        cmd = build_preview_command("test.txt")
        assert cmd == ["head", "-n", "100", "test.txt"]

    def test_build_preview_command_custom_lines(self):
        """Test preview command with custom line count."""
        cmd = build_preview_command("test.txt", lines=50)
        assert cmd == ["head", "-n", "50", "test.txt"]

    def test_build_preview_command_max_lines_limit(self):
        """Test preview command respects 500 line maximum."""
        cmd = build_preview_command("test.txt", lines=1000)
        assert cmd == ["head", "-n", "500", "test.txt"]

    def test_build_command_preview(self):
        """Test build_command correctly handles preview tool."""
        cmd = build_command("preview", {"path": "data/file.md", "lines": 200})
        assert cmd == ["head", "-n", "200", "data/file.md"]

    def test_build_command_preview_default(self):
        """Test build_command with preview using defaults."""
        cmd = build_command("preview", {"path": "readme.txt"})
        assert cmd == ["head", "-n", "100", "readme.txt"]

    def test_build_command_preview_exceeds_max(self):
        """Test build_command enforces max line limit."""
        cmd = build_command("preview", {"path": "big.log", "lines": 999})
        assert cmd == ["head", "-n", "500", "big.log"]


class TestPreviewToolDefinition:
    """Tests for the preview tool definition in BASH_TOOLS."""

    def test_preview_tool_exists(self):
        """Test that preview tool is defined in BASH_TOOLS."""
        tool_names = [t["function"]["name"] for t in BASH_TOOLS]
        assert "preview" in tool_names

    def test_preview_tool_has_correct_description(self):
        """Test preview tool has PREFERRED indicator in description."""
        preview_tool = next(
            t for t in BASH_TOOLS if t["function"]["name"] == "preview"
        )
        assert "PREFERRED" in preview_tool["function"]["description"]

    def test_preview_tool_parameters(self):
        """Test preview tool has correct parameters."""
        preview_tool = next(
            t for t in BASH_TOOLS if t["function"]["name"] == "preview"
        )
        params = preview_tool["function"]["parameters"]

        assert "path" in params["properties"]
        assert "lines" in params["properties"]
        assert params["properties"]["lines"]["default"] == 100
        assert params["required"] == ["path"]


class TestCatToolDescription:
    """Tests for the updated cat tool description."""

    def test_cat_tool_has_warning(self):
        """Test that cat tool description includes warning."""
        cat_tool = next(t for t in BASH_TOOLS if t["function"]["name"] == "cat")
        description = cat_tool["function"]["description"]

        assert "WARNING" in description
        assert "preview" in description.lower()


class TestToolRegistry:
    """Tests for preview tool in the tool registry."""

    def test_registry_has_preview_tool(self):
        """Test that default registry includes preview tool."""
        registry = create_default_registry()
        assert "preview" in registry

    def test_registry_preview_is_cacheable(self):
        """Test that preview tool is marked as cacheable."""
        registry = create_default_registry()
        assert registry.is_cacheable("preview") is True

    def test_registry_preview_builds_command(self):
        """Test that registry builds correct preview command."""
        registry = create_default_registry()
        cmd = registry.build_command("preview", {"path": "test.md", "lines": 75})
        assert cmd == ["head", "-n", "75", "test.md"]


class TestFilesystemAgentPreview:
    """Tests for the FilesystemAgent._execute_preview method."""

    @pytest.fixture
    def mock_sandbox(self):
        """Create a mock sandbox executor."""
        sandbox = AsyncMock()
        return sandbox

    @pytest.fixture
    def mock_client(self):
        """Create a mock OpenAI client."""
        return AsyncMock()

    @pytest.fixture
    def agent(self, mock_client, mock_sandbox, tmp_path):
        """Create a FilesystemAgent for testing."""
        return FilesystemAgent(
            client=mock_client,
            deployment_name="test-model",
            data_root=tmp_path,
            sandbox=mock_sandbox,
            parallel_execution=False,
        )

    @pytest.mark.asyncio
    async def test_execute_preview_returns_metadata(self, agent, mock_sandbox, tmp_path):
        """Test that preview returns content with metadata."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        # Mock sandbox responses
        mock_sandbox.execute = AsyncMock(side_effect=[
            # wc -l response
            ExecutionResult(
                success=True,
                stdout="3 " + str(test_file),
                stderr="",
                return_code=0,
                command="wc -l",
                error=None,
            ),
            # head response
            ExecutionResult(
                success=True,
                stdout="line1\nline2\nline3\n",
                stderr="",
                return_code=0,
                command="head -n 100",
                error=None,
            ),
        ])

        tool_call = ToolCall(
            id="test-1",
            name="preview",
            arguments={"path": "test.txt"},
        )

        result = await agent._execute_preview(tool_call)

        assert result.success is True
        assert "line1" in result.stdout
        assert "Preview:" in result.stdout
        assert "3 lines" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_preview_shows_cat_hint_for_large_file(
        self, agent, mock_sandbox, tmp_path
    ):
        """Test that preview shows hint to use cat for large files."""
        test_file = tmp_path / "large.txt"
        # Simulate a file larger than 100 lines
        test_file.write_text("line\n" * 500)

        mock_sandbox.execute = AsyncMock(side_effect=[
            # wc -l response - 500 lines
            ExecutionResult(
                success=True,
                stdout="500 " + str(test_file),
                stderr="",
                return_code=0,
                command="wc -l",
                error=None,
            ),
            # head response - first 100 lines
            ExecutionResult(
                success=True,
                stdout="line\n" * 100,
                stderr="",
                return_code=0,
                command="head -n 100",
                error=None,
            ),
        ])

        tool_call = ToolCall(
            id="test-2",
            name="preview",
            arguments={"path": "large.txt"},
        )

        result = await agent._execute_preview(tool_call)

        assert result.success is True
        assert "100 of 500 lines" in result.stdout
        assert "Use 'cat large.txt' for full content" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_preview_no_cat_hint_for_small_file(
        self, agent, mock_sandbox, tmp_path
    ):
        """Test that preview doesn't show cat hint for small files."""
        test_file = tmp_path / "small.txt"
        test_file.write_text("line1\nline2\n")

        mock_sandbox.execute = AsyncMock(side_effect=[
            # wc -l response - 2 lines (less than preview limit)
            ExecutionResult(
                success=True,
                stdout="2 " + str(test_file),
                stderr="",
                return_code=0,
                command="wc -l",
                error=None,
            ),
            # head response
            ExecutionResult(
                success=True,
                stdout="line1\nline2\n",
                stderr="",
                return_code=0,
                command="head -n 100",
                error=None,
            ),
        ])

        tool_call = ToolCall(
            id="test-3",
            name="preview",
            arguments={"path": "small.txt", "lines": 100},
        )

        result = await agent._execute_preview(tool_call)

        assert result.success is True
        assert "Use 'cat" not in result.stdout  # No hint for small files

    @pytest.mark.asyncio
    async def test_execute_preview_handles_error(self, agent, mock_sandbox, tmp_path):
        """Test that preview handles errors gracefully."""
        tool_call = ToolCall(
            id="test-4",
            name="preview",
            arguments={"path": "nonexistent.txt"},
        )

        # Configure mock to raise an exception (simulating sandbox failure)
        mock_sandbox.execute = AsyncMock(
            side_effect=FileNotFoundError("nonexistent.txt not found")
        )

        result = await agent._execute_preview(tool_call)

        assert result.success is False
        assert "PreviewError" in (result.error or "")
        assert "nonexistent.txt" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_tool_routes_preview(self, agent, mock_sandbox, tmp_path):
        """Test that _execute_tool correctly routes to _execute_preview."""
        test_file = tmp_path / "routed.txt"
        test_file.write_text("content\n")

        mock_sandbox.execute = AsyncMock(side_effect=[
            ExecutionResult(
                success=True,
                stdout="1 " + str(test_file),
                stderr="",
                return_code=0,
                command="wc -l",
                error=None,
            ),
            ExecutionResult(
                success=True,
                stdout="content\n",
                stderr="",
                return_code=0,
                command="head -n 100",
                error=None,
            ),
        ])

        tool_call = ToolCall(
            id="test-5",
            name="preview",
            arguments={"path": "routed.txt"},
        )

        result = await agent._execute_tool(tool_call)

        assert result.success is True
        assert "Preview:" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_preview_custom_lines(self, agent, mock_sandbox, tmp_path):
        """Test preview with custom line count."""
        test_file = tmp_path / "custom.txt"
        test_file.write_text("line\n" * 200)

        mock_sandbox.execute = AsyncMock(side_effect=[
            ExecutionResult(
                success=True,
                stdout="200 " + str(test_file),
                stderr="",
                return_code=0,
                command="wc -l",
                error=None,
            ),
            ExecutionResult(
                success=True,
                stdout="line\n" * 50,
                stderr="",
                return_code=0,
                command="head -n 50",
                error=None,
            ),
        ])

        tool_call = ToolCall(
            id="test-6",
            name="preview",
            arguments={"path": "custom.txt", "lines": 50},
        )

        result = await agent._execute_preview(tool_call)

        assert result.success is True
        assert "50 of 200 lines" in result.stdout
