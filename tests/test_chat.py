"""Tests for chat API routes with repository integration.

This test suite covers:
- Chat endpoint with session management via repository
- Session clearing and history retrieval
- Repository dependency injection
- Concurrent access handling
- Backward compatibility with existing functionality
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import reset_dependencies, get_session_repository
from app.repositories.session_repository import SessionRepository
from app.agent.filesystem_agent import AgentResponse, ToolCall


@pytest.fixture
def client():
    """Provide a test client."""
    return TestClient(app)


@pytest.fixture
def mock_agent():
    """Provide a mock filesystem agent."""
    agent = MagicMock()

    # Mock chat method
    async def mock_chat(user_message, history=None):
        return AgentResponse(
            message="I found 3 files",
            tool_calls=[
                ToolCall(id="call_1", name="find", arguments={"path": ".", "name": "*.md"})
            ],
            tool_results=[
                {
                    "tool_call_id": "call_1",
                    "tool_name": "find",
                    "result": {"output": "file1.md\nfile2.md\nfile3.md", "success": True}
                }
            ]
        )

    agent.chat = AsyncMock(side_effect=mock_chat)
    return agent


@pytest.fixture(autouse=True)
def reset_deps():
    """Reset dependencies before and after each test."""
    reset_dependencies()
    yield
    reset_dependencies()


class TestChatEndpoint:
    """Test cases for POST /chat endpoint with repository."""

    @patch("app.api.routes.chat.create_agent")
    def test_chat_creates_new_session(self, mock_create_agent, client, mock_agent):
        """Test that chat creates a new session if none provided."""
        mock_create_agent.return_value = mock_agent

        response = client.post(
            "/api/chat",
            json={"message": "Find markdown files"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["response"] == "I found 3 files"
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["name"] == "find"

    @patch("app.api.routes.chat.create_agent")
    def test_chat_uses_existing_session(self, mock_create_agent, client, mock_agent):
        """Test that chat reuses an existing session."""
        mock_create_agent.return_value = mock_agent

        # First request
        response1 = client.post(
            "/api/chat",
            json={"message": "First message"}
        )
        session_id = response1.json()["session_id"]

        # Second request with same session
        response2 = client.post(
            "/api/chat",
            json={"message": "Second message", "session_id": session_id}
        )

        assert response2.status_code == 200
        assert response2.json()["session_id"] == session_id

        # Verify history was passed to agent (should have first message)
        call_args = mock_agent.chat.call_args_list[1]
        history = call_args[1]["history"]
        assert len(history) == 2  # First user + assistant message
        assert history[0]["content"] == "First message"

    @patch("app.api.routes.chat.create_agent")
    def test_chat_maintains_conversation_history(self, mock_create_agent, client, mock_agent):
        """Test that chat maintains conversation history in repository."""
        mock_create_agent.return_value = mock_agent

        # Send multiple messages
        response1 = client.post(
            "/api/chat",
            json={"message": "Message 1"}
        )
        session_id = response1.json()["session_id"]

        client.post(
            "/api/chat",
            json={"message": "Message 2", "session_id": session_id}
        )

        client.post(
            "/api/chat",
            json={"message": "Message 3", "session_id": session_id}
        )

        # Get history
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")
        history = history_response.json()["history"]

        assert len(history) == 6  # 3 user + 3 assistant messages
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Message 1"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "Message 2"

    @patch("app.api.routes.chat.create_agent")
    def test_chat_with_invalid_message(self, mock_create_agent, client, mock_agent):
        """Test chat with invalid message returns validation error."""
        mock_create_agent.return_value = mock_agent

        # Empty message
        response = client.post(
            "/api/chat",
            json={"message": ""}
        )

        assert response.status_code == 422  # Validation error

    @patch("app.api.routes.chat.create_agent")
    def test_chat_updates_session_in_repository(self, mock_create_agent, client, mock_agent):
        """Test that chat correctly updates session in repository."""
        mock_create_agent.return_value = mock_agent

        response = client.post(
            "/api/chat",
            json={"message": "Test message"}
        )

        session_id = response.json()["session_id"]

        # Verify session was created in repository
        session_repo = get_session_repository()

        # Use asyncio to call async methods
        async def verify_session():
            session = await session_repo.get(session_id)
            assert session is not None
            assert len(session.messages) == 2  # User + assistant
            assert session.messages[0]["role"] == "user"
            assert session.messages[0]["content"] == "Test message"
            assert session.messages[1]["role"] == "assistant"

        asyncio.run(verify_session())


class TestSessionEndpoints:
    """Test cases for session management endpoints."""

    @patch("app.api.routes.chat.create_agent")
    def test_get_session_history(self, mock_create_agent, client, mock_agent):
        """Test getting session history."""
        mock_create_agent.return_value = mock_agent

        # Create session
        response = client.post(
            "/api/chat",
            json={"message": "Test message"}
        )
        session_id = response.json()["session_id"]

        # Get history
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")

        assert history_response.status_code == 200
        data = history_response.json()
        assert data["session_id"] == session_id
        assert len(data["history"]) == 2

    def test_get_nonexistent_session_history(self, client):
        """Test getting history for nonexistent session returns 404."""
        response = client.get("/api/chat/sessions/nonexistent/history")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("app.api.routes.chat.create_agent")
    def test_clear_session(self, mock_create_agent, client, mock_agent):
        """Test clearing a session."""
        mock_create_agent.return_value = mock_agent

        # Create session with messages
        response = client.post(
            "/api/chat",
            json={"message": "Test message"}
        )
        session_id = response.json()["session_id"]

        # Clear session
        clear_response = client.delete(f"/api/chat/sessions/{session_id}")

        assert clear_response.status_code == 200
        assert "cleared" in clear_response.json()["message"].lower()

        # Verify history is empty
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")
        assert len(history_response.json()["history"]) == 0

    def test_clear_nonexistent_session(self, client):
        """Test clearing a nonexistent session returns 404."""
        response = client.delete("/api/chat/sessions/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestRepositoryInjection:
    """Test cases for dependency injection of repository."""

    @patch("app.api.routes.chat.create_agent")
    def test_repository_singleton_behavior(self, mock_create_agent, client, mock_agent):
        """Test that repository is a singleton across requests."""
        mock_create_agent.return_value = mock_agent

        # Create session in first request
        response1 = client.post(
            "/api/chat",
            json={"message": "Message 1"}
        )
        session_id = response1.json()["session_id"]

        # Access same session in second request
        response2 = client.get(f"/api/chat/sessions/{session_id}/history")

        assert response2.status_code == 200
        # Session should be found, proving repository is shared

    @patch("app.api.routes.chat.create_agent")
    def test_reset_dependencies_clears_repository(self, mock_create_agent, client, mock_agent):
        """Test that reset_dependencies clears the repository singleton."""
        mock_create_agent.return_value = mock_agent

        # Create session
        response = client.post(
            "/api/chat",
            json={"message": "Test"}
        )
        session_id = response.json()["session_id"]

        # Reset dependencies
        reset_dependencies()

        # Try to access session - should not exist (new repository instance)
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")

        assert history_response.status_code == 404


class TestConcurrentAccess:
    """Test cases for concurrent access to sessions."""

    @patch("app.api.routes.chat.create_agent")
    def test_concurrent_requests_same_session(self, mock_create_agent, client, mock_agent):
        """Test concurrent requests to same session are handled safely."""
        mock_create_agent.return_value = mock_agent

        # Create session
        response = client.post(
            "/api/chat",
            json={"message": "Initial message"}
        )
        session_id = response.json()["session_id"]

        # Make concurrent requests to same session
        import concurrent.futures

        def make_request(n):
            return client.post(
                "/api/chat",
                json={"message": f"Concurrent message {n}", "session_id": session_id}
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.status_code == 200 for r in results)

        # Verify all messages are in history
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")
        history = history_response.json()["history"]

        # Should have initial message (2) + 5 concurrent (10) = 12 messages
        assert len(history) == 12

    @patch("app.api.routes.chat.create_agent")
    def test_concurrent_requests_different_sessions(self, mock_create_agent, client, mock_agent):
        """Test concurrent requests to different sessions don't interfere."""
        mock_create_agent.return_value = mock_agent

        # Make concurrent requests with different sessions
        import concurrent.futures

        def make_request(n):
            return client.post(
                "/api/chat",
                json={"message": f"Message {n}"}
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in futures]

        # All should succeed with different session IDs
        assert all(r.status_code == 200 for r in results)
        session_ids = [r.json()["session_id"] for r in results]
        assert len(set(session_ids)) == 5  # All unique


class TestBackwardCompatibility:
    """Test cases for backward compatibility with existing functionality."""

    @patch("app.api.routes.chat.create_agent")
    def test_tool_calls_response_format(self, mock_create_agent, client, mock_agent):
        """Test that tool calls are returned in expected format."""
        mock_create_agent.return_value = mock_agent

        response = client.post(
            "/api/chat",
            json={"message": "Find files"}
        )

        data = response.json()
        assert "tool_calls" in data
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["id"] == "call_1"
        assert data["tool_calls"][0]["name"] == "find"
        assert "arguments" in data["tool_calls"][0]

    @patch("app.api.routes.chat.create_agent")
    def test_tool_results_response_format(self, mock_create_agent, client, mock_agent):
        """Test that tool results are returned in expected format."""
        mock_create_agent.return_value = mock_agent

        response = client.post(
            "/api/chat",
            json={"message": "Find files"}
        )

        data = response.json()
        assert "tool_results" in data
        assert len(data["tool_results"]) == 1
        assert data["tool_results"][0]["tool_call_id"] == "call_1"
        assert data["tool_results"][0]["tool_name"] == "find"
        assert "result" in data["tool_results"][0]

    @patch("app.api.routes.chat.create_agent")
    def test_response_message_format(self, mock_create_agent, client, mock_agent):
        """Test that response message is in expected format."""
        mock_create_agent.return_value = mock_agent

        response = client.post(
            "/api/chat",
            json={"message": "Test"}
        )

        data = response.json()
        assert "response" in data
        assert isinstance(data["response"], str)
        assert "session_id" in data


class TestMessageTruncation:
    """Test cases for message history truncation."""

    @patch("app.api.routes.chat.create_agent")
    def test_session_truncates_at_max_messages(self, mock_create_agent, client, mock_agent):
        """Test that session truncates messages at max limit (50)."""
        mock_create_agent.return_value = mock_agent

        # Create session
        response = client.post(
            "/api/chat",
            json={"message": "Initial"}
        )
        session_id = response.json()["session_id"]

        # Send 30 more messages (60 total messages = 30 * 2)
        for i in range(30):
            client.post(
                "/api/chat",
                json={"message": f"Message {i}", "session_id": session_id}
            )

        # Get history
        history_response = client.get(f"/api/chat/sessions/{session_id}/history")
        history = history_response.json()["history"]

        # Should be truncated to 50
        assert len(history) == 50
        # Should keep most recent messages
        assert "Message 29" in str(history)
