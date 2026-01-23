"""Tests for session repository implementation.

This test suite covers:
- Session domain model functionality
- SessionRepository CRUD operations
- get_or_create convenience method
- TTL-based cleanup
- Concurrent access and locking behavior
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.repositories.session_repository import Session, SessionRepository


class TestSessionModel:
    """Test cases for the Session domain model."""

    def test_session_initialization(self):
        """Test that a session is initialized with default values."""
        session = Session(id="test-123")

        assert session.id == "test-123"
        assert session.messages == []
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_accessed, datetime)
        assert session.max_messages == 50

    def test_session_custom_max_messages(self):
        """Test creating a session with custom max_messages."""
        session = Session(id="test-123", max_messages=100)

        assert session.max_messages == 100

    def test_add_message(self):
        """Test adding a message to session history."""
        session = Session(id="test-123")
        initial_time = session.last_accessed

        # Sleep briefly to ensure timestamp changes
        import time
        time.sleep(0.01)

        session.add_message("user", "Hello, world!")

        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello, world!"
        assert session.last_accessed > initial_time

    def test_add_message_with_kwargs(self):
        """Test adding a message with additional fields."""
        session = Session(id="test-123")

        session.add_message(
            "assistant",
            "I used tools",
            tool_calls=["grep", "find"]
        )

        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "assistant"
        assert session.messages[0]["content"] == "I used tools"
        assert session.messages[0]["tool_calls"] == ["grep", "find"]

    def test_message_truncation(self):
        """Test that messages are truncated when exceeding max_messages."""
        session = Session(id="test-123", max_messages=5)

        # Add 10 messages
        for i in range(10):
            session.add_message("user", f"Message {i}")

        # Should only keep last 5
        assert len(session.messages) == 5
        assert session.messages[0]["content"] == "Message 5"
        assert session.messages[-1]["content"] == "Message 9"

    def test_get_history(self):
        """Test getting a copy of message history."""
        session = Session(id="test-123")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")

        history = session.get_history()

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

        # Verify it's a copy
        history.append({"role": "user", "content": "Test"})
        assert len(session.messages) == 2

    def test_clear(self):
        """Test clearing all messages from session."""
        session = Session(id="test-123")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")

        initial_time = session.last_accessed
        import time
        time.sleep(0.01)

        session.clear()

        assert len(session.messages) == 0
        assert session.last_accessed > initial_time


class TestSessionRepository:
    """Test cases for SessionRepository CRUD operations."""

    @pytest.fixture
    async def repository(self):
        """Provide a fresh repository for each test."""
        return SessionRepository(ttl_seconds=3600, max_messages=50)

    async def test_repository_initialization(self, repository):
        """Test repository is initialized with correct defaults."""
        assert repository.ttl == timedelta(seconds=3600)
        assert repository.max_messages == 50
        count = await repository.count()
        assert count == 0

    async def test_add_session(self, repository):
        """Test adding a new session."""
        session = Session(id="test-123")

        result = await repository.add(session)

        assert result.id == "test-123"
        count = await repository.count()
        assert count == 1

    async def test_get_session(self, repository):
        """Test getting a session by ID."""
        session = Session(id="test-123")
        await repository.add(session)

        retrieved = await repository.get("test-123")

        assert retrieved is not None
        assert retrieved.id == "test-123"

    async def test_get_nonexistent_session(self, repository):
        """Test getting a session that doesn't exist."""
        result = await repository.get("nonexistent")

        assert result is None

    async def test_get_updates_last_accessed(self, repository):
        """Test that get() updates the last_accessed timestamp."""
        session = Session(id="test-123")
        initial_time = session.last_accessed
        await repository.add(session)

        await asyncio.sleep(0.01)
        retrieved = await repository.get("test-123")

        assert retrieved.last_accessed > initial_time

    async def test_get_all(self, repository):
        """Test getting all sessions."""
        session1 = Session(id="test-1")
        session2 = Session(id="test-2")
        await repository.add(session1)
        await repository.add(session2)

        all_sessions = await repository.get_all()

        assert len(all_sessions) == 2
        ids = {s.id for s in all_sessions}
        assert ids == {"test-1", "test-2"}

    async def test_update_session(self, repository):
        """Test updating an existing session."""
        session = Session(id="test-123")
        await repository.add(session)

        # Modify and update
        session.add_message("user", "Hello")
        result = await repository.update("test-123", session)

        assert result is not None
        retrieved = await repository.get("test-123")
        assert len(retrieved.messages) == 1

    async def test_update_nonexistent_session(self, repository):
        """Test updating a session that doesn't exist."""
        session = Session(id="nonexistent")

        result = await repository.update("nonexistent", session)

        assert result is None

    async def test_delete_session(self, repository):
        """Test deleting a session."""
        session = Session(id="test-123")
        await repository.add(session)

        deleted = await repository.delete("test-123")

        assert deleted is True
        exists = await repository.exists("test-123")
        assert exists is False

    async def test_delete_nonexistent_session(self, repository):
        """Test deleting a session that doesn't exist."""
        deleted = await repository.delete("nonexistent")

        assert deleted is False

    async def test_exists(self, repository):
        """Test checking if a session exists."""
        session = Session(id="test-123")

        exists_before = await repository.exists("test-123")
        assert exists_before is False

        await repository.add(session)

        exists_after = await repository.exists("test-123")
        assert exists_after is True

    async def test_count(self, repository):
        """Test counting sessions."""
        assert await repository.count() == 0

        await repository.add(Session(id="test-1"))
        assert await repository.count() == 1

        await repository.add(Session(id="test-2"))
        assert await repository.count() == 2

        await repository.delete("test-1")
        assert await repository.count() == 1


class TestGetOrCreate:
    """Test cases for get_or_create convenience method."""

    @pytest.fixture
    async def repository(self):
        """Provide a fresh repository for each test."""
        return SessionRepository(ttl_seconds=3600, max_messages=50)

    async def test_get_or_create_new_session(self, repository):
        """Test get_or_create creates a new session if not exists."""
        session = await repository.get_or_create("test-123")

        assert session.id == "test-123"
        assert len(session.messages) == 0
        assert session.max_messages == 50

        count = await repository.count()
        assert count == 1

    async def test_get_or_create_existing_session(self, repository):
        """Test get_or_create returns existing session."""
        # Create initial session
        initial = await repository.get_or_create("test-123")
        initial.add_message("user", "Hello")

        # Get same session
        retrieved = await repository.get_or_create("test-123")

        assert retrieved.id == "test-123"
        assert len(retrieved.messages) == 1
        assert retrieved.messages[0]["content"] == "Hello"

        count = await repository.count()
        assert count == 1

    async def test_get_or_create_updates_last_accessed(self, repository):
        """Test get_or_create updates last_accessed for existing sessions."""
        session = await repository.get_or_create("test-123")
        initial_time = session.last_accessed

        await asyncio.sleep(0.01)
        retrieved = await repository.get_or_create("test-123")

        assert retrieved.last_accessed > initial_time


class TestCleanupExpired:
    """Test cases for TTL-based cleanup."""

    @pytest.fixture
    async def repository(self):
        """Provide a repository with short TTL for testing."""
        return SessionRepository(ttl_seconds=1, max_messages=50)

    async def test_cleanup_no_expired_sessions(self, repository):
        """Test cleanup when no sessions are expired."""
        await repository.add(Session(id="test-1"))
        await repository.add(Session(id="test-2"))

        removed = await repository.cleanup_expired()

        assert removed == 0
        assert await repository.count() == 2

    async def test_cleanup_expired_sessions(self, repository):
        """Test cleanup removes expired sessions."""
        # Add sessions
        session1 = Session(id="test-1")
        session2 = Session(id="test-2")

        # Manually set last_accessed to past
        past_time = datetime.now(UTC) - timedelta(seconds=2)
        session1.last_accessed = past_time
        session2.last_accessed = past_time

        await repository.add(session1)
        await repository.add(session2)

        removed = await repository.cleanup_expired()

        assert removed == 2
        assert await repository.count() == 0

    async def test_cleanup_mixed_sessions(self, repository):
        """Test cleanup with mix of expired and active sessions."""
        # Add expired session
        expired_session = Session(id="expired")
        expired_session.last_accessed = datetime.now(UTC) - timedelta(seconds=2)
        await repository.add(expired_session)

        # Add active session
        active_session = Session(id="active")
        await repository.add(active_session)

        removed = await repository.cleanup_expired()

        assert removed == 1
        assert await repository.count() == 1
        assert await repository.exists("active")
        assert not await repository.exists("expired")


class TestConcurrentAccess:
    """Test cases for concurrent access and locking behavior."""

    @pytest.fixture
    async def repository(self):
        """Provide a fresh repository for each test."""
        return SessionRepository(ttl_seconds=3600, max_messages=50)

    async def test_concurrent_get_or_create(self, repository):
        """Test concurrent get_or_create calls don't create duplicates."""
        # Simulate 10 concurrent get_or_create calls
        tasks = [
            repository.get_or_create("test-123")
            for _ in range(10)
        ]

        sessions = await asyncio.gather(*tasks)

        # All should have the same ID
        for session in sessions:
            assert session.id == "test-123"

        # Only one session should be created
        count = await repository.count()
        assert count == 1

    async def test_concurrent_add_messages(self, repository):
        """Test concurrent message additions to same session."""
        session = await repository.get_or_create("test-123")

        async def add_message(n: int):
            session = await repository.get("test-123")
            session.add_message("user", f"Message {n}")
            await repository.update("test-123", session)

        # Add 10 messages concurrently
        tasks = [add_message(i) for i in range(10)]
        await asyncio.gather(*tasks)

        final_session = await repository.get("test-123")
        assert len(final_session.messages) == 10

    async def test_concurrent_different_sessions(self, repository):
        """Test concurrent operations on different sessions don't block each other."""
        async def create_and_modify(session_id: str):
            session = await repository.get_or_create(session_id)
            session.add_message("user", f"Hello from {session_id}")
            await repository.update(session_id, session)
            return session_id

        # Create 5 different sessions concurrently
        tasks = [create_and_modify(f"test-{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert await repository.count() == 5

        # Verify each session has its message
        for i in range(5):
            session = await repository.get(f"test-{i}")
            assert len(session.messages) == 1
            assert f"test-{i}" in session.messages[0]["content"]

    async def test_concurrent_cleanup(self, repository):
        """Test concurrent cleanup operations."""
        # Add some sessions
        for i in range(5):
            await repository.add(Session(id=f"test-{i}"))

        # Run cleanup concurrently
        tasks = [repository.cleanup_expired() for _ in range(3)]
        results = await asyncio.gather(*tasks)

        # All should return 0 (no expired sessions)
        assert all(r == 0 for r in results)
        assert await repository.count() == 5


class TestSessionLocking:
    """Test cases for session locking behavior."""

    @pytest.fixture
    async def repository(self):
        """Provide a fresh repository for each test."""
        return SessionRepository(ttl_seconds=3600, max_messages=50)

    async def test_per_session_lock_creation(self, repository):
        """Test that locks are created per session."""
        session1 = Session(id="test-1")
        session2 = Session(id="test-2")

        await repository.add(session1)
        await repository.add(session2)

        # Verify locks were created
        assert "test-1" in repository._locks
        assert "test-2" in repository._locks
        assert repository._locks["test-1"] is not repository._locks["test-2"]

    async def test_lock_removed_on_delete(self, repository):
        """Test that lock is removed when session is deleted."""
        session = Session(id="test-123")
        await repository.add(session)

        assert "test-123" in repository._locks

        await repository.delete("test-123")

        assert "test-123" not in repository._locks

    async def test_sequential_access_to_same_session(self, repository):
        """Test sequential access to same session works correctly."""
        await repository.get_or_create("test-123")

        session1 = await repository.get("test-123")
        session1.add_message("user", "Message 1")
        await repository.update("test-123", session1)

        session2 = await repository.get("test-123")
        session2.add_message("user", "Message 2")
        await repository.update("test-123", session2)

        final = await repository.get("test-123")
        assert len(final.messages) == 2
