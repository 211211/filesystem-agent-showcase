"""
Tests for the /api/chat/stream endpoint and chat_stream method.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import json

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.agent.filesystem_agent import FilesystemAgent, ToolCall
from app.sandbox.executor import SandboxExecutor, ExecutionResult


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        (test_dir / "test.txt").write_text("Hello, World!")
        (test_dir / "data.md").write_text("# Sample\n\nThis is a test file.")
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


class TestChatStreamMethod:
    """Tests for the FilesystemAgent.chat_stream method."""

    @pytest.mark.asyncio
    async def test_chat_stream_yields_status_first(self, agent, mock_openai_client):
        """Test that chat_stream yields a status event first."""
        # Mock a simple response without tool calls
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = None

        mock_chunk_done = MagicMock()
        mock_chunk_done.choices = [MagicMock()]
        mock_chunk_done.choices[0].delta.content = None
        mock_chunk_done.choices[0].delta.tool_calls = None
        mock_chunk_done.choices[0].finish_reason = "stop"

        async def mock_stream():
            yield mock_chunk
            yield mock_chunk_done

        mock_response = MagicMock()
        mock_response.__aiter__ = mock_stream
        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Collect events
        events = []
        async for event_type, event_data in agent.chat_stream("Hello"):
            events.append((event_type, event_data))

        # First event should be status
        assert events[0][0] == "status"
        assert events[0][1]["stage"] == "thinking"

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens(self, agent, mock_openai_client):
        """Test that chat_stream yields token events for LLM output."""
        # Mock streaming response with multiple tokens
        chunks = []
        for content in ["Hello", " ", "World", "!"]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = content
            chunk.choices[0].delta.tool_calls = None
            chunk.choices[0].finish_reason = None
            chunks.append(chunk)

        # Add final chunk
        final_chunk = MagicMock()
        final_chunk.choices = [MagicMock()]
        final_chunk.choices[0].delta.content = None
        final_chunk.choices[0].delta.tool_calls = None
        final_chunk.choices[0].finish_reason = "stop"
        chunks.append(final_chunk)

        class MockStream:
            def __init__(self, chunks):
                self.chunks = chunks
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.index]
                self.index += 1
                return chunk

        mock_openai_client.chat.completions.create = AsyncMock(return_value=MockStream(chunks))

        # Collect token events
        tokens = []
        async for event_type, event_data in agent.chat_stream("Hello"):
            if event_type == "token":
                tokens.append(event_data["content"])

        assert len(tokens) == 4
        assert "".join(tokens) == "Hello World!"

    @pytest.mark.asyncio
    async def test_chat_stream_yields_done_event(self, agent, mock_openai_client):
        """Test that chat_stream yields a done event at the end."""
        # Mock simple response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Done"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = None

        mock_chunk_done = MagicMock()
        mock_chunk_done.choices = [MagicMock()]
        mock_chunk_done.choices[0].delta.content = None
        mock_chunk_done.choices[0].delta.tool_calls = None
        mock_chunk_done.choices[0].finish_reason = "stop"

        class MockStream:
            def __init__(self):
                self.chunks = [mock_chunk, mock_chunk_done]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.index]
                self.index += 1
                return chunk

        mock_openai_client.chat.completions.create = AsyncMock(return_value=MockStream())

        # Collect events
        events = []
        async for event_type, event_data in agent.chat_stream("Hello"):
            events.append((event_type, event_data))

        # Last event should be done
        assert events[-1][0] == "done"
        assert "message" in events[-1][1]
        assert "tool_calls_count" in events[-1][1]

    @pytest.mark.asyncio
    async def test_chat_stream_error_handling(self, agent, mock_openai_client):
        """Test that chat_stream yields error event on exception."""
        # Mock an error
        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Collect events
        events = []
        async for event_type, event_data in agent.chat_stream("Hello"):
            events.append((event_type, event_data))

        # Should have error event
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "API Error" in error_events[0][1]["message"]


class TestChatStreamEndpoint:
    """Tests for the /api/chat/stream endpoint."""

    def test_endpoint_exists(self):
        """Test that the stream endpoint is registered."""
        from app.main import app

        routes = [route.path for route in app.routes]
        # Check for chat routes - they are mounted under /api
        assert any("/chat" in str(route) for route in app.routes)

    @pytest.mark.asyncio
    async def test_stream_endpoint_returns_sse(self, temp_data_dir):
        """Test that the stream endpoint returns SSE content type."""
        from app.main import app
        from app.config import get_settings

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment_name = "gpt-4"
        mock_settings.azure_openai_api_version = "2024-02-15"
        mock_settings.data_root = temp_data_dir
        mock_settings.sandbox_enabled = True
        mock_settings.command_timeout = 30
        mock_settings.max_file_size = 1048576
        mock_settings.max_output_size = 102400
        mock_settings.parallel_execution = True
        mock_settings.max_concurrent_tools = 5
        mock_settings.cache_enabled = True
        mock_settings.cache_ttl = 300
        mock_settings.cache_max_size = 100

        app.dependency_overrides[get_settings] = lambda: mock_settings

        # Use TestClient to make request
        with patch("app.api.routes.chat.create_agent") as mock_create_agent:
            # Setup mock agent
            mock_agent = AsyncMock()

            async def mock_chat_stream(message, history):
                yield ("status", {"stage": "thinking", "message": "Analyzing..."})
                yield ("token", {"content": "Hello"})
                yield ("done", {"message": "Hello", "tool_calls_count": 0, "iterations": 1})

            mock_agent.chat_stream = mock_chat_stream
            mock_create_agent.return_value = mock_agent

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/chat/stream",
                    json={"message": "Hello"},
                )

                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

        # Clean up
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_stream_endpoint_sse_format(self, temp_data_dir):
        """Test that the stream endpoint returns properly formatted SSE events."""
        from app.main import app
        from app.config import get_settings

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com/"
        mock_settings.azure_openai_deployment_name = "gpt-4"
        mock_settings.azure_openai_api_version = "2024-02-15"
        mock_settings.data_root = temp_data_dir
        mock_settings.sandbox_enabled = True
        mock_settings.command_timeout = 30
        mock_settings.max_file_size = 1048576
        mock_settings.max_output_size = 102400
        mock_settings.parallel_execution = True
        mock_settings.max_concurrent_tools = 5
        mock_settings.cache_enabled = True
        mock_settings.cache_ttl = 300
        mock_settings.cache_max_size = 100

        app.dependency_overrides[get_settings] = lambda: mock_settings

        with patch("app.api.routes.chat.create_agent") as mock_create_agent:
            mock_agent = AsyncMock()

            async def mock_chat_stream(message, history):
                yield ("status", {"stage": "thinking", "message": "Analyzing..."})
                yield ("token", {"content": "Test"})
                yield ("done", {"message": "Test", "tool_calls_count": 0, "iterations": 1})

            mock_agent.chat_stream = mock_chat_stream
            mock_create_agent.return_value = mock_agent

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/chat/stream",
                    json={"message": "Hello"},
                )

                content = response.text

                # Verify SSE format
                assert "event: status" in content
                assert "event: token" in content
                assert "event: done" in content
                assert "data: " in content

        app.dependency_overrides.clear()


class TestSSEEventGenerator:
    """Tests for the SSE event generator function."""

    @pytest.mark.asyncio
    async def test_sse_event_adds_session_id(self, agent, mock_openai_client):
        """Test that SSE events include session_id."""
        from app.api.routes.chat import sse_event_generator

        # Mock simple response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hi"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = None

        mock_chunk_done = MagicMock()
        mock_chunk_done.choices = [MagicMock()]
        mock_chunk_done.choices[0].delta.content = None
        mock_chunk_done.choices[0].delta.tool_calls = None
        mock_chunk_done.choices[0].finish_reason = "stop"

        class MockStream:
            def __init__(self):
                self.chunks = [mock_chunk, mock_chunk_done]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.index]
                self.index += 1
                return chunk

        mock_openai_client.chat.completions.create = AsyncMock(return_value=MockStream())

        session_id = "test-session-123"

        # Collect SSE events
        events = []
        async for sse in sse_event_generator(agent, "Hello", session_id, []):
            events.append(sse)

        # Verify session_id is in events
        for event in events:
            if "data: " in event:
                # Parse the JSON data
                data_start = event.find("data: ") + 6
                data_end = event.find("\n\n", data_start)
                if data_end == -1:
                    data_end = len(event)
                data_str = event[data_start:data_end].strip()
                if data_str:
                    data = json.loads(data_str)
                    assert data.get("session_id") == session_id


class TestChatStreamWithToolCalls:
    """Tests for chat_stream handling tool calls."""

    @pytest.mark.asyncio
    async def test_chat_stream_with_tool_call(self, agent, mock_openai_client, sandbox, temp_data_dir):
        """Test chat_stream yields tool_call and tool_result events."""
        # First response with tool call
        tool_call_chunk = MagicMock()
        tool_call_chunk.choices = [MagicMock()]
        tool_call_chunk.choices[0].delta.content = None
        tool_call_chunk.choices[0].delta.tool_calls = [MagicMock()]
        tool_call_chunk.choices[0].delta.tool_calls[0].index = 0
        tool_call_chunk.choices[0].delta.tool_calls[0].id = "call_123"
        tool_call_chunk.choices[0].delta.tool_calls[0].function = MagicMock()
        tool_call_chunk.choices[0].delta.tool_calls[0].function.name = "cat"
        tool_call_chunk.choices[0].delta.tool_calls[0].function.arguments = '{"path": "test.txt"}'
        tool_call_chunk.choices[0].finish_reason = None

        tool_call_done = MagicMock()
        tool_call_done.choices = [MagicMock()]
        tool_call_done.choices[0].delta.content = None
        tool_call_done.choices[0].delta.tool_calls = None
        tool_call_done.choices[0].finish_reason = "tool_calls"

        # Second response after tool execution
        response_chunk = MagicMock()
        response_chunk.choices = [MagicMock()]
        response_chunk.choices[0].delta.content = "The file contains: Hello"
        response_chunk.choices[0].delta.tool_calls = None
        response_chunk.choices[0].finish_reason = None

        response_done = MagicMock()
        response_done.choices = [MagicMock()]
        response_done.choices[0].delta.content = None
        response_done.choices[0].delta.tool_calls = None
        response_done.choices[0].finish_reason = "stop"

        call_count = [0]

        class MockStreamFirst:
            def __init__(self):
                self.chunks = [tool_call_chunk, tool_call_done]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.index]
                self.index += 1
                return chunk

        class MockStreamSecond:
            def __init__(self):
                self.chunks = [response_chunk, response_done]
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.chunks):
                    raise StopAsyncIteration
                chunk = self.chunks[self.index]
                self.index += 1
                return chunk

        async def mock_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockStreamFirst()
            else:
                return MockStreamSecond()

        mock_openai_client.chat.completions.create = mock_create

        # Collect events
        events = []
        async for event_type, event_data in agent.chat_stream("Read test.txt"):
            events.append((event_type, event_data))

        # Verify we have tool_call events
        event_types = [e[0] for e in events]
        assert "status" in event_types
        # Tool call should be present
        tool_call_events = [e for e in events if e[0] == "tool_call"]
        assert len(tool_call_events) >= 1

        # Tool result should be present
        tool_result_events = [e for e in events if e[0] == "tool_result"]
        assert len(tool_result_events) >= 1

        # Done should be last
        assert events[-1][0] == "done"
