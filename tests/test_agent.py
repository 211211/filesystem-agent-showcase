"""
Tests for the filesystem agent.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from app.agent.filesystem_agent import (
    FilesystemAgent,
    Message,
    ToolCall,
    AgentResponse,
    create_agent,
)
from app.sandbox.executor import SandboxExecutor, ExecutionResult


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        (test_dir / "test.txt").write_text("Hello, World!")
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
def agent(mock_openai_client, sandbox, temp_data_dir):
    """Create a filesystem agent for testing."""
    return FilesystemAgent(
        client=mock_openai_client,
        deployment_name="test-deployment",
        data_root=temp_data_dir,
        sandbox=sandbox,
        max_tool_iterations=5,
    )


class TestMessage:
    """Tests for Message dataclass."""

    def test_basic_message(self):
        """Test creating a basic message."""
        msg = Message(role="user", content="Hello")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"

    def test_message_with_tool_calls(self):
        """Test message with tool calls."""
        msg = Message(
            role="assistant",
            content="Let me search...",
            tool_calls=[{"id": "1", "type": "function"}],
        )
        d = msg.to_dict()
        assert "tool_calls" in d

    def test_tool_message(self):
        """Test tool response message."""
        msg = Message(
            role="tool",
            content="File contents...",
            tool_call_id="call_123",
        )
        d = msg.to_dict()
        assert d["tool_call_id"] == "call_123"


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_tool_call_to_dict(self):
        """Test converting tool call to dict."""
        tc = ToolCall(id="1", name="grep", arguments={"pattern": "TODO", "path": "."})
        d = tc.to_dict()
        assert d["id"] == "1"
        assert d["name"] == "grep"
        assert d["arguments"]["pattern"] == "TODO"


class TestAgentResponse:
    """Tests for AgentResponse dataclass."""

    def test_basic_response(self):
        """Test basic agent response."""
        resp = AgentResponse(message="Here are the results")
        d = resp.to_dict()
        assert d["message"] == "Here are the results"
        assert d["tool_calls"] == []
        assert d["tool_results"] == []

    def test_response_with_tools(self):
        """Test response with tool calls and results."""
        tc = ToolCall(id="1", name="ls", arguments={"path": "."})
        resp = AgentResponse(
            message="Found files",
            tool_calls=[tc],
            tool_results=[{"tool_call_id": "1", "tool_name": "ls", "result": {}}],
        )
        d = resp.to_dict()
        assert len(d["tool_calls"]) == 1
        assert len(d["tool_results"]) == 1


class TestFilesystemAgent:
    """Tests for the FilesystemAgent class."""

    @pytest.mark.asyncio
    async def test_chat_without_tools(self, agent, mock_openai_client):
        """Test chat when LLM doesn't use tools."""
        # Mock the response without tool calls
        mock_message = MagicMock()
        mock_message.tool_calls = None
        mock_message.content = "The data directory contains test files."

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Execute chat
        result = await agent.chat("What's in the data directory?")

        # Verify
        assert result.message == "The data directory contains test files."
        assert len(result.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_execute_tool(self, agent, temp_data_dir):
        """Test executing a single tool."""
        tc = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await agent._execute_tool(tc)

        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_invalid_tool(self, agent):
        """Test executing an invalid tool."""
        tc = ToolCall(id="1", name="invalid_cmd", arguments={"path": "."})
        result = await agent._execute_tool(tc)

        assert not result.success
        assert "error" in result.error.lower() or result.stderr

    def test_parse_tool_calls(self, agent):
        """Test parsing tool calls from LLM response."""
        # Create mock response message with tool calls
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "ls"
        mock_tool_call.function.arguments = '{"path": "."}'

        mock_message = MagicMock()
        mock_message.tool_calls = [mock_tool_call]

        # Parse
        tool_calls = agent._parse_tool_calls(mock_message)

        assert len(tool_calls) == 1
        assert tool_calls[0].id == "call_123"
        assert tool_calls[0].name == "ls"
        assert tool_calls[0].arguments["path"] == "."

    def test_parse_empty_tool_calls(self, agent):
        """Test parsing when there are no tool calls."""
        mock_message = MagicMock()
        mock_message.tool_calls = None

        tool_calls = agent._parse_tool_calls(mock_message)
        assert tool_calls == []


class TestCreateAgent:
    """Tests for the create_agent factory function."""

    def test_create_agent_returns_agent(self, temp_data_dir):
        """Test that create_agent returns a FilesystemAgent instance."""
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
        assert agent.data_root == temp_data_dir
        assert agent.deployment_name == "gpt-4"
