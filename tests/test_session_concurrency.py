"""
Tests for session management concurrency in chat routes.

These tests verify that the asyncio.Lock protection on _sessions
correctly handles concurrent access scenarios.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile

from app.api.routes.chat import (
    _sessions,
    _sessions_lock,
    chat,
    clear_session,
    get_session_history,
    ChatRequest,
)
from app.agent.filesystem_agent import FilesystemAgent, AgentResponse, ToolCall


@pytest.fixture(autouse=True)
async def clear_sessions():
    """Clear sessions before and after each test."""
    async with _sessions_lock:
        _sessions.clear()
    yield
    async with _sessions_lock:
        _sessions.clear()


@pytest.fixture
def mock_agent():
    """Create a mock FilesystemAgent that simulates realistic delay."""
    agent = AsyncMock(spec=FilesystemAgent)

    async def mock_chat(user_message: str, history=None):
        # Simulate realistic LLM response time (helps trigger race conditions)
        await asyncio.sleep(0.01)
        return AgentResponse(
            message=f"Response to: {user_message}",
            tool_calls=[],
            tool_results=[],
        )

    agent.chat = mock_chat
    return agent


class TestConcurrentSessionWrites:
    """Tests for concurrent write operations to the same session."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_same_session_no_data_loss(self, mock_agent):
        """
        Test that concurrent requests to the same session_id
        don't lose messages due to race conditions.

        This is the primary test for the C3 fix.
        """
        session_id = "test-concurrent-session"
        num_requests = 10

        async def make_request(i: int):
            request = ChatRequest(
                message=f"Message {i}",
                session_id=session_id,
            )
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                # Simulate dependency injection
                response = await chat(request, mock_agent)
                return response

        # Launch all requests concurrently
        tasks = [make_request(i) for i in range(num_requests)]
        responses = await asyncio.gather(*tasks)

        # All requests should succeed
        assert len(responses) == num_requests

        # Check session history - should have all messages (user + assistant pairs)
        async with _sessions_lock:
            history = _sessions.get(session_id, [])

        # Each request adds 2 messages (user + assistant)
        # With history limit of 50, we expect min(num_requests * 2, 50) messages
        expected_messages = min(num_requests * 2, 50)
        assert len(history) == expected_messages, (
            f"Expected {expected_messages} messages, got {len(history)}. "
            f"Data loss detected!"
        )

        # Verify message content integrity
        user_messages = [h["content"] for h in history if h["role"] == "user"]
        assert len(user_messages) == min(num_requests, 25), (
            f"Expected {min(num_requests, 25)} user messages, got {len(user_messages)}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_requests_different_sessions_isolated(self, mock_agent):
        """Test that concurrent requests to different sessions are isolated."""
        num_sessions = 5
        requests_per_session = 3

        async def make_request(session_id: str, msg_id: int):
            request = ChatRequest(
                message=f"Session {session_id} Message {msg_id}",
                session_id=session_id,
            )
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                return await chat(request, mock_agent)

        # Launch requests to multiple sessions concurrently
        tasks = []
        for s in range(num_sessions):
            session_id = f"session-{s}"
            for m in range(requests_per_session):
                tasks.append(make_request(session_id, m))

        await asyncio.gather(*tasks)

        # Verify each session has correct history
        for s in range(num_sessions):
            session_id = f"session-{s}"
            async with _sessions_lock:
                history = _sessions.get(session_id, [])

            # Each session should have requests_per_session * 2 messages
            assert len(history) == requests_per_session * 2, (
                f"Session {session_id} has {len(history)} messages, "
                f"expected {requests_per_session * 2}"
            )

            # Verify messages belong to this session
            for h in history:
                if h["role"] == "user":
                    assert f"Session {session_id}" in h["content"]

    @pytest.mark.asyncio
    async def test_history_limit_enforced_under_concurrent_load(self, mock_agent):
        """Test that history limit (50) is enforced even under concurrent load."""
        session_id = "test-limit-session"
        num_requests = 40  # 40 * 2 = 80 messages, should be limited to 50

        async def make_request(i: int):
            request = ChatRequest(
                message=f"Message {i}",
                session_id=session_id,
            )
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                return await chat(request, mock_agent)

        tasks = [make_request(i) for i in range(num_requests)]
        await asyncio.gather(*tasks)

        async with _sessions_lock:
            history = _sessions.get(session_id, [])

        # Should never exceed 50 messages
        assert len(history) <= 50, (
            f"History exceeded limit: {len(history)} > 50"
        )


class TestConcurrentSessionReads:
    """Tests for concurrent read operations."""

    @pytest.mark.asyncio
    async def test_concurrent_history_reads_safe(self):
        """Test that concurrent reads of session history are safe."""
        session_id = "test-read-session"

        # Pre-populate session
        async with _sessions_lock:
            _sessions[session_id] = [
                {"role": "user", "content": f"Message {i}"}
                for i in range(10)
            ]

        async def read_history():
            return await get_session_history(session_id)

        # Concurrent reads should all succeed and return same data
        tasks = [read_history() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All reads should return identical history
        for result in results:
            assert len(result["history"]) == 10
            assert result["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_read_returns_copy_not_reference(self):
        """Test that read returns a copy, so external modifications don't affect internal state."""
        session_id = "test-copy-session"

        async with _sessions_lock:
            _sessions[session_id] = [{"role": "user", "content": "Original"}]

        # Get history
        result = await get_session_history(session_id)

        # Modify the returned history
        result["history"].append({"role": "user", "content": "Injected"})

        # Internal state should be unchanged
        async with _sessions_lock:
            internal_history = _sessions[session_id]

        assert len(internal_history) == 1, "Internal state was modified by external code"
        assert internal_history[0]["content"] == "Original"


class TestConcurrentSessionDeletes:
    """Tests for concurrent delete operations."""

    @pytest.mark.asyncio
    async def test_concurrent_deletes_same_session_no_error(self):
        """Test that concurrent deletes of the same session don't raise errors."""
        session_id = "test-delete-session"

        # Pre-populate session
        async with _sessions_lock:
            _sessions[session_id] = [{"role": "user", "content": "Test"}]

        async def try_delete():
            try:
                return await clear_session(session_id)
            except Exception as e:
                return {"error": str(e)}

        # Only one should succeed, others should get 404
        tasks = [try_delete() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and 404s
        successes = [r for r in results if isinstance(r, dict) and "message" in r]
        errors = [r for r in results if isinstance(r, Exception) or (isinstance(r, dict) and "error" in r)]

        # Exactly one should succeed
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"

        # Session should be deleted
        async with _sessions_lock:
            assert session_id not in _sessions

    @pytest.mark.asyncio
    async def test_delete_during_concurrent_writes(self, mock_agent):
        """Test behavior when delete happens during concurrent writes."""
        session_id = "test-delete-during-write"

        async def write_request():
            request = ChatRequest(
                message="Test message",
                session_id=session_id,
            )
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                try:
                    return await chat(request, mock_agent)
                except Exception as e:
                    return {"error": str(e)}

        async def delete_request():
            await asyncio.sleep(0.005)  # Small delay to let writes start
            try:
                return await clear_session(session_id)
            except Exception:
                return {"deleted": False}

        # Launch writes and a delete concurrently
        write_tasks = [write_request() for _ in range(5)]
        delete_task = delete_request()

        results = await asyncio.gather(*write_tasks, delete_task, return_exceptions=True)

        # All operations should complete without crashing
        for result in results:
            assert not isinstance(result, Exception), f"Operation failed: {result}"


class TestConcurrentMixedOperations:
    """Tests for mixed concurrent operations."""

    @pytest.mark.asyncio
    async def test_read_write_delete_concurrent(self, mock_agent):
        """Test concurrent reads, writes, and deletes across multiple sessions."""
        num_sessions = 3

        # Pre-populate some sessions
        for i in range(num_sessions):
            async with _sessions_lock:
                _sessions[f"session-{i}"] = [
                    {"role": "user", "content": f"Initial {i}"}
                ]

        async def write_op(session_id: str):
            request = ChatRequest(message="Write op", session_id=session_id)
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                try:
                    return await chat(request, mock_agent)
                except Exception as e:
                    return {"error": str(e)}

        async def read_op(session_id: str):
            try:
                return await get_session_history(session_id)
            except Exception:
                return {"history": []}

        async def delete_op(session_id: str):
            try:
                return await clear_session(session_id)
            except Exception:
                return {"deleted": False}

        # Create a mix of operations
        tasks = []
        for i in range(num_sessions):
            session_id = f"session-{i}"
            tasks.extend([
                write_op(session_id),
                write_op(session_id),
                read_op(session_id),
                read_op(session_id),
            ])

        # Add one delete at the end
        tasks.append(delete_op("session-0"))

        # All operations should complete without deadlock or crash
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # No exceptions should have been raised
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Operations raised exceptions: {exceptions}"


class TestRaceConditionScenarios:
    """Tests that specifically target the race condition that was fixed."""

    @pytest.mark.asyncio
    async def test_interleaved_read_modify_write_pattern(self, mock_agent):
        """
        Test the specific race condition pattern:
        1. Request A reads history
        2. Request B reads history (same state)
        3. Request A writes updated history
        4. Request B writes updated history (should NOT overwrite A's changes)
        """
        session_id = "test-race-condition"

        # Track the order of operations
        operation_log = []

        async def mock_chat_with_delay(user_message: str, history=None, delay: float = 0):
            operation_log.append(f"start-{user_message}")
            await asyncio.sleep(delay)
            operation_log.append(f"end-{user_message}")
            return AgentResponse(
                message=f"Response to: {user_message}",
                tool_calls=[],
                tool_results=[],
            )

        # Create two agents with different delays to force interleaving
        agent_a = AsyncMock(spec=FilesystemAgent)
        agent_a.chat = lambda user_message, history=None: mock_chat_with_delay(user_message, history, 0.02)

        agent_b = AsyncMock(spec=FilesystemAgent)
        agent_b.chat = lambda user_message, history=None: mock_chat_with_delay(user_message, history, 0.01)

        async def request_a():
            request = ChatRequest(message="A", session_id=session_id)
            with patch("app.api.routes.chat.get_agent", return_value=agent_a):
                return await chat(request, agent_a)

        async def request_b():
            # Small delay so A starts first
            await asyncio.sleep(0.005)
            request = ChatRequest(message="B", session_id=session_id)
            with patch("app.api.routes.chat.get_agent", return_value=agent_b):
                return await chat(request, agent_b)

        # Run both concurrently
        await asyncio.gather(request_a(), request_b())

        # Both messages should be in history (no data loss)
        async with _sessions_lock:
            history = _sessions.get(session_id, [])

        user_messages = [h["content"] for h in history if h["role"] == "user"]

        # Both A and B should be present
        assert "A" in user_messages, "Message A was lost in race condition"
        assert "B" in user_messages, "Message B was lost in race condition"
        assert len(history) == 4, f"Expected 4 messages (2 pairs), got {len(history)}"

    @pytest.mark.asyncio
    async def test_high_contention_stress_test(self, mock_agent):
        """Stress test with high contention on a single session."""
        session_id = "stress-test-session"
        num_concurrent = 50

        async def make_request(i: int):
            request = ChatRequest(
                message=f"Stress-{i}",
                session_id=session_id,
            )
            with patch("app.api.routes.chat.get_agent", return_value=mock_agent):
                return await chat(request, mock_agent)

        # Launch many concurrent requests
        tasks = [make_request(i) for i in range(num_concurrent)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # No exceptions
        exceptions = [r for r in responses if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Stress test raised exceptions: {exceptions}"

        # Session should have messages (up to limit of 50)
        async with _sessions_lock:
            history = _sessions.get(session_id, [])

        # Should have exactly 50 messages (limit enforced)
        assert len(history) == 50, f"Expected 50 messages, got {len(history)}"

        # All should be valid messages
        for h in history:
            assert h["role"] in ["user", "assistant"]
            assert "content" in h
