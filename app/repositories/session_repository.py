"""Session repository implementation for managing chat sessions.

This module provides a thread-safe, in-memory repository for chat session management
with automatic TTL-based cleanup and per-session locking for concurrent access.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional

from app.repositories.base import Repository


@dataclass
class Session:
    """Domain model for a chat session.

    A session maintains conversation history with automatic message truncation
    and last-access tracking for TTL cleanup.

    Attributes:
        id: Unique session identifier
        messages: List of message dictionaries with role and content
        created_at: Timestamp when session was created
        last_accessed: Timestamp when session was last accessed
        max_messages: Maximum number of messages to retain (older ones are truncated)
    """

    id: str
    messages: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
    max_messages: int = 50

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to the session history.

        Messages are automatically truncated if they exceed max_messages limit.
        The last_accessed timestamp is updated.

        Args:
            role: Message role (e.g., "user", "assistant", "system")
            content: Message content
            **kwargs: Additional message fields (tool_calls, etc.)
        """
        self.messages.append({
            "role": role,
            "content": content,
            **kwargs
        })
        self.last_accessed = datetime.now(UTC)

        # Truncate if exceeds max
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_history(self) -> List[Dict]:
        """Get a copy of the message history.

        Returns:
            A copy of the messages list
        """
        return self.messages.copy()

    def clear(self) -> None:
        """Clear all messages from the session.

        The last_accessed timestamp is updated.
        """
        self.messages = []
        self.last_accessed = datetime.now(UTC)


class SessionRepository(Repository[Session]):
    """In-memory session repository with per-session locking.

    This repository provides thread-safe access to chat sessions with:
    - Per-session locking for concurrent message operations
    - Global lock for repository-level operations
    - TTL-based automatic cleanup of expired sessions
    - get_or_create convenience method

    The repository uses asyncio.Lock to ensure thread safety without blocking
    other sessions during concurrent operations.

    Attributes:
        ttl: Timedelta representing session time-to-live
        max_messages: Default max messages for new sessions
    """

    def __init__(self, ttl_seconds: int = 3600, max_messages: int = 50):
        """Initialize the session repository.

        Args:
            ttl_seconds: Session time-to-live in seconds (default: 1 hour)
            max_messages: Maximum messages per session (default: 50)
        """
        self._sessions: Dict[str, Session] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_messages = max_messages

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create lock for a specific session.

        This method uses the global lock to safely create per-session locks.

        Args:
            session_id: The session identifier

        Returns:
            The asyncio.Lock for the specified session
        """
        async with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def get(self, id: str) -> Optional[Session]:
        """Get session by ID.

        Updates the last_accessed timestamp if the session is found.

        Args:
            id: The session identifier

        Returns:
            The session if found, None otherwise
        """
        lock = await self._get_lock(id)
        async with lock:
            session = self._sessions.get(id)
            if session:
                session.last_accessed = datetime.now(UTC)
            return session

    async def get_or_create(self, id: str) -> Session:
        """Get existing session or create a new one.

        This is a convenience method that combines get and add operations.
        If the session exists, its last_accessed is updated. If not, a new
        session is created with the configured max_messages.

        Args:
            id: The session identifier

        Returns:
            The existing or newly created session
        """
        lock = await self._get_lock(id)
        async with lock:
            if id not in self._sessions:
                self._sessions[id] = Session(
                    id=id,
                    max_messages=self.max_messages
                )
            session = self._sessions[id]
            session.last_accessed = datetime.now(UTC)
            return session

    async def get_all(self) -> List[Session]:
        """Get all sessions.

        Returns:
            List of all sessions in the repository
        """
        async with self._global_lock:
            return list(self._sessions.values())

    async def add(self, entity: Session) -> Session:
        """Add a new session.

        Args:
            entity: The session to add

        Returns:
            The added session
        """
        lock = await self._get_lock(entity.id)
        async with lock:
            self._sessions[entity.id] = entity
            return entity

    async def update(self, id: str, entity: Session) -> Optional[Session]:
        """Update an existing session.

        Args:
            id: The session identifier
            entity: The updated session data

        Returns:
            The updated session if found, None otherwise
        """
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                self._sessions[id] = entity
                return entity
            return None

    async def delete(self, id: str) -> bool:
        """Delete session by ID.

        Also removes the associated lock from the lock dictionary.

        Args:
            id: The session identifier

        Returns:
            True if deleted, False if session was not found
        """
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                del self._sessions[id]
                # Also remove the lock
                async with self._global_lock:
                    self._locks.pop(id, None)
                return True
            return False

    async def exists(self, id: str) -> bool:
        """Check if session exists.

        Args:
            id: The session identifier

        Returns:
            True if session exists, False otherwise
        """
        async with self._global_lock:
            return id in self._sessions

    async def cleanup_expired(self) -> int:
        """Remove expired sessions based on TTL.

        Sessions are considered expired if their last_accessed timestamp
        is older than the configured TTL.

        Returns:
            The number of sessions removed
        """
        now = datetime.now(UTC)
        expired_ids = []

        async with self._global_lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed > self.ttl:
                    expired_ids.append(session_id)

        for session_id in expired_ids:
            await self.delete(session_id)

        return len(expired_ids)

    async def count(self) -> int:
        """Get total session count.

        Returns:
            The number of sessions in the repository
        """
        async with self._global_lock:
            return len(self._sessions)
