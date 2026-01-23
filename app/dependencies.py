"""Dependency injection functions for FastAPI.

This module provides dependency injection for the application, including:
- Settings singleton
- SessionRepository singleton
- ToolRegistry singleton
- AgentFactory singleton
- FilesystemAgent creation
- Utility functions for testing (reset_dependencies)
"""

from functools import lru_cache
from typing import Optional

from app.settings import Settings
from app.repositories.session_repository import SessionRepository
from app.repositories.tool_registry import ToolRegistry, create_default_registry
from app.factories.agent_factory import AgentFactory, get_agent_factory, reset_agent_factory
from app.agent.filesystem_agent import FilesystemAgent


# Settings dependency
@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: The application settings loaded from environment
    """
    return Settings()


# Session repository singleton
_session_repository: Optional[SessionRepository] = None


def get_session_repository() -> SessionRepository:
    """Get or create session repository singleton.

    This function provides a singleton SessionRepository instance for
    the entire application. The repository is initialized with default
    TTL (1 hour) and max messages (50).

    Returns:
        SessionRepository: The singleton session repository instance
    """
    global _session_repository
    if _session_repository is None:
        _session_repository = SessionRepository(
            ttl_seconds=3600,  # 1 hour TTL
            max_messages=50
        )
    return _session_repository


# Tool registry singleton
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create tool registry singleton.

    This function provides a singleton ToolRegistry instance with all
    default bash tools (grep, find, cat, head, tail, ls, wc) pre-registered.

    Returns:
        ToolRegistry: The singleton tool registry instance
    """
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = create_default_registry()
    return _tool_registry


def get_agent_factory_dependency() -> AgentFactory:
    """Get or create agent factory singleton.

    This function provides a singleton AgentFactory instance for creating
    FilesystemAgent instances with proper dependency injection.

    Returns:
        AgentFactory: The singleton agent factory instance
    """
    # Use the factory's built-in singleton pattern
    return get_agent_factory()


def get_agent(settings: Optional[Settings] = None) -> FilesystemAgent:
    """Create a FilesystemAgent instance using the factory.

    This function is compatible with FastAPI's Depends() and creates
    a new agent instance on each call using the factory pattern.

    Args:
        settings: Optional settings override. If not provided, uses get_settings()

    Returns:
        FilesystemAgent: A configured agent instance

    Example:
        ```python
        # In FastAPI route
        @router.post("/chat")
        async def chat(
            agent: FilesystemAgent = Depends(get_agent),
            settings: Settings = Depends(get_settings)
        ):
            response = await agent.chat(message)
            return response
        ```
    """
    if settings is None:
        settings = get_settings()

    factory = get_agent_factory_dependency()
    return factory.create_from_settings(settings)


def reset_dependencies() -> None:
    """Reset all dependency singletons (for testing).

    This function clears all singleton instances, forcing them to be
    recreated on next access. Use this in test fixtures to ensure
    clean state between tests.

    Warning:
        This should only be called in test environments. Calling this
        in production will reset all session data and factory state.
    """
    global _session_repository, _tool_registry
    _session_repository = None
    _tool_registry = None

    # Clear lru_cache for settings
    get_settings.cache_clear()

    # Reset factory singletons
    reset_agent_factory()
