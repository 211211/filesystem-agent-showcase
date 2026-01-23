"""Factory pattern implementation for agent creation.

This module provides factory classes for creating FilesystemAgent instances
with proper dependency injection and testability.
"""

from app.factories.component_factory import (
    ComponentFactory,
    DefaultComponentFactory,
    TestComponentFactory,
)
from app.factories.agent_factory import (
    AgentFactory,
    get_agent_factory,
    reset_agent_factory,
)

__all__ = [
    "ComponentFactory",
    "DefaultComponentFactory",
    "TestComponentFactory",
    "AgentFactory",
    "get_agent_factory",
    "reset_agent_factory",
]
