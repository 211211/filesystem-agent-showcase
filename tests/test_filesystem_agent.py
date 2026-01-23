"""
Tests for FilesystemAgent with ToolRegistry injection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from app.agent.filesystem_agent import (
    FilesystemAgent,
    ToolCall,
    create_agent,
)
from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.repositories.tool_registry import ToolRegistry, ToolDefinition, ToolParameter


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        (test_dir / "test.txt").write_text("Hello, World!")
        (test_dir / "example.py").write_text("print('test')")
        yield test_dir


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    return AsyncMock()


@pytest.fixture
def sandbox(temp_data_dir):
    """Create a sandbox executor for testing."""
    return SandboxExecutor(root_path=temp_data_dir, timeout=10, enabled=True)


@pytest.fixture
def tool_registry():
    """Create a tool registry with test tools."""
    registry = ToolRegistry()

    # Register cat tool
    registry.register(ToolDefinition(
        name="cat",
        description="Display file contents",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
        ],
        builder=lambda args: ["cat", args["path"]],
        cacheable=True,
        cache_ttl=0
    ))

    # Register grep tool
    registry.register(ToolDefinition(
        name="grep",
        description="Search for a pattern in files",
        parameters=[
            ToolParameter("pattern", "string", "The regex pattern to search for"),
            ToolParameter("path", "string", "File or directory path to search"),
            ToolParameter("recursive", "boolean", "Search recursively", False, True),
            ToolParameter("ignore_case", "boolean", "Case insensitive search", False, False),
        ],
        builder=lambda args: [
            "grep",
            "-n" if True else "",
            "-r" if args.get("recursive", True) else "",
            "-i" if args.get("ignore_case", False) else "",
            args["pattern"],
            args["path"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    # Register ls tool
    registry.register(ToolDefinition(
        name="ls",
        description="List directory contents",
        parameters=[
            ToolParameter("path", "string", "Directory path to list"),
            ToolParameter("all", "boolean", "Show hidden files", False, False),
        ],
        builder=lambda args: [
            "ls",
            "-a" if args.get("all", False) else "",
            args["path"]
        ],
        cacheable=False
    ))

    return registry


@pytest.fixture
def agent_with_registry(mock_openai_client, sandbox, temp_data_dir, tool_registry):
    """Create a filesystem agent with tool registry."""
    return FilesystemAgent(
        client=mock_openai_client,
        deployment_name="test-deployment",
        data_root=temp_data_dir,
        sandbox=sandbox,
        max_tool_iterations=5,
        tool_registry=tool_registry,
    )


@pytest.fixture
def agent_without_registry(mock_openai_client, sandbox, temp_data_dir):
    """Create a filesystem agent without tool registry (legacy mode)."""
    return FilesystemAgent(
        client=mock_openai_client,
        deployment_name="test-deployment",
        data_root=temp_data_dir,
        sandbox=sandbox,
        max_tool_iterations=5,
        tool_registry=None,  # Explicitly None for legacy mode
    )


class TestFilesystemAgentWithRegistry:
    """Tests for FilesystemAgent with injected ToolRegistry."""

    def test_get_tools_with_registry(self, agent_with_registry, tool_registry):
        """Test that get_tools returns tools from registry in OpenAI format."""
        tools = agent_with_registry.get_tools()

        assert isinstance(tools, list)
        assert len(tools) == len(tool_registry)

        # Verify format
        for tool in tools:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_get_tools_returns_correct_tool_names(self, agent_with_registry):
        """Test that get_tools returns correct tool names."""
        tools = agent_with_registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]

        assert "cat" in tool_names
        assert "grep" in tool_names
        assert "ls" in tool_names

    def test_build_command_with_registry(self, agent_with_registry):
        """Test that _build_command uses registry."""
        # Test cat command
        cmd = agent_with_registry._build_command("cat", {"path": "test.txt"})
        assert cmd == ["cat", "test.txt"]

        # Test grep command
        cmd = agent_with_registry._build_command("grep", {
            "pattern": "TODO",
            "path": ".",
            "recursive": True,
            "ignore_case": False
        })
        assert "grep" in cmd
        assert "TODO" in cmd

    def test_build_command_unknown_tool(self, agent_with_registry):
        """Test that _build_command raises error for unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            agent_with_registry._build_command("unknown_tool", {})

    @pytest.mark.asyncio
    async def test_execute_tool_with_registry(self, agent_with_registry):
        """Test executing a tool with registry."""
        tc = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await agent_with_registry._execute_tool(tc)

        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_chat_uses_registry_tools(self, agent_with_registry, mock_openai_client):
        """Test that chat() uses tools from registry."""
        # Mock the response without tool calls
        mock_message = MagicMock()
        mock_message.tool_calls = None
        mock_message.content = "The file contains test data."

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Execute chat
        result = await agent_with_registry.chat("What's in test.txt?")

        # Verify that create was called with tools from registry
        call_args = mock_openai_client.chat.completions.create.call_args
        assert "tools" in call_args.kwargs
        tools = call_args.kwargs["tools"]
        assert len(tools) == 3  # cat, grep, ls

        # Verify result
        assert result.message == "The file contains test data."


class TestFilesystemAgentWithoutRegistry:
    """Tests for FilesystemAgent without ToolRegistry (legacy mode)."""

    def test_get_tools_without_registry(self, agent_without_registry):
        """Test that get_tools returns legacy BASH_TOOLS when no registry."""
        from app.agent.tools.bash_tools import BASH_TOOLS

        tools = agent_without_registry.get_tools()

        assert tools == BASH_TOOLS
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_build_command_without_registry(self, agent_without_registry):
        """Test that _build_command uses legacy build_command (Head-First pattern)."""
        # Test cat command - now uses head -n 100 by default
        cmd = agent_without_registry._build_command("cat", {"path": "test.txt"})
        assert cmd == ["head", "-n", "100", "test.txt"]

        # Test cat with full flag
        cmd = agent_without_registry._build_command("cat", {"path": "test.txt", "full": True})
        assert cmd == ["cat", "test.txt"]

        # Test grep command
        cmd = agent_without_registry._build_command("grep", {
            "pattern": "TODO",
            "path": ".",
            "recursive": True,
            "ignore_case": False
        })
        assert "grep" in cmd
        assert "TODO" in cmd

    @pytest.mark.asyncio
    async def test_execute_tool_without_registry(self, agent_without_registry):
        """Test executing a tool without registry (legacy mode)."""
        tc = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await agent_without_registry._execute_tool(tc)

        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_chat_uses_legacy_tools(self, agent_without_registry, mock_openai_client):
        """Test that chat() uses legacy BASH_TOOLS when no registry."""
        from app.agent.tools.bash_tools import BASH_TOOLS

        # Mock the response
        mock_message = MagicMock()
        mock_message.tool_calls = None
        mock_message.content = "Found files."

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Execute chat
        result = await agent_without_registry.chat("What files are here?")

        # Verify that create was called with legacy BASH_TOOLS
        call_args = mock_openai_client.chat.completions.create.call_args
        assert "tools" in call_args.kwargs
        tools = call_args.kwargs["tools"]
        assert tools == BASH_TOOLS


class TestCreateAgentBackwardCompatibility:
    """Tests for create_agent factory function backward compatibility."""

    def test_create_agent_without_registry(self, temp_data_dir):
        """Test that create_agent works without registry (backward compatibility)."""
        agent = create_agent(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4",
            api_version="2024-02-15-preview",
            data_root=temp_data_dir,
            sandbox_enabled=True,
            command_timeout=30,
        )

        assert isinstance(agent, FilesystemAgent)
        assert agent.tool_registry is None  # No registry by default
        assert agent.data_root == temp_data_dir
        assert agent.deployment_name == "gpt-4"

    def test_create_agent_get_tools_legacy(self, temp_data_dir):
        """Test that create_agent result uses legacy tools."""
        from app.agent.tools.bash_tools import BASH_TOOLS

        agent = create_agent(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4",
            api_version="2024-02-15-preview",
            data_root=temp_data_dir,
        )

        tools = agent.get_tools()
        assert tools == BASH_TOOLS


class TestRegistryToolExecution:
    """Integration tests for executing tools via registry."""

    @pytest.mark.asyncio
    async def test_registry_cat_execution(self, agent_with_registry, temp_data_dir):
        """Test executing cat via registry."""
        tc = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await agent_with_registry._execute_tool(tc)

        assert result.success
        assert result.stdout == "Hello, World!"
        assert result.return_code == 0

    @pytest.mark.asyncio
    async def test_registry_grep_execution(self, agent_with_registry, temp_data_dir):
        """Test executing grep via registry."""
        tc = ToolCall(id="1", name="grep", arguments={
            "pattern": "test",
            "path": "example.py",
            "recursive": False,
            "ignore_case": False
        })
        result = await agent_with_registry._execute_tool(tc)

        assert result.success
        assert "test" in result.stdout

    @pytest.mark.asyncio
    async def test_registry_ls_execution(self, agent_with_registry, temp_data_dir):
        """Test executing ls via registry."""
        tc = ToolCall(id="1", name="ls", arguments={
            "path": ".",
            "all": False
        })
        result = await agent_with_registry._execute_tool(tc)

        assert result.success
        assert "test.txt" in result.stdout or "example.py" in result.stdout
