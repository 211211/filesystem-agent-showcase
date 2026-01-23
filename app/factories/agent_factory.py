"""
Agent Factory for creating FilesystemAgent instances.
Provides centralized agent creation with dependency injection.
"""

from typing import Optional

from app.config.agent_config import AgentConfig
from app.config import Settings
from app.factories.component_factory import ComponentFactory, DefaultComponentFactory
from app.repositories.tool_registry import ToolRegistry, create_default_registry
from app.agent.filesystem_agent import FilesystemAgent


class AgentFactory:
    """Factory for creating FilesystemAgent instances with injected dependencies."""

    def __init__(
        self,
        component_factory: Optional[ComponentFactory] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        """
        Initialize agent factory.

        Args:
            component_factory: Factory for creating components (default: DefaultComponentFactory)
            tool_registry: Tool registry for agent (default: create_default_registry())
        """
        self.component_factory = component_factory or DefaultComponentFactory()
        self.tool_registry = tool_registry or create_default_registry()

    def create(self, config: AgentConfig) -> FilesystemAgent:
        """
        Create fully configured agent from config.

        Args:
            config: Agent configuration

        Returns:
            Configured FilesystemAgent instance
        """
        # Create components using factory
        client = self.component_factory.create_client(config.openai)
        executor = self.component_factory.create_executor(config.sandbox)
        cache_manager = self.component_factory.create_cache_manager(config.cache)
        orchestrator = self.component_factory.create_orchestrator(
            config.orchestrator,
            executor,
        )

        # Create agent with all components
        return FilesystemAgent(
            client=client,
            deployment_name=config.openai.deployment_name,
            data_root=config.sandbox.root_path,
            sandbox=executor,
            max_tool_iterations=config.max_tool_iterations,
            parallel_execution=config.orchestrator.parallel_enabled,
            max_concurrent_tools=config.orchestrator.max_concurrent_tools,
            cache_manager=cache_manager,
        )

    def create_from_settings(self, settings: Settings) -> FilesystemAgent:
        """
        Create agent from application settings.

        Args:
            settings: Application settings

        Returns:
            Configured FilesystemAgent instance
        """
        config = AgentConfig.from_settings(settings)
        return self.create(config)


# Singleton instance
_agent_factory: Optional[AgentFactory] = None


def get_agent_factory(
    component_factory: Optional[ComponentFactory] = None,
    tool_registry: Optional[ToolRegistry] = None,
) -> AgentFactory:
    """
    Get or create agent factory singleton.

    Args:
        component_factory: Optional component factory (only used on first call)
        tool_registry: Optional tool registry (only used on first call)

    Returns:
        AgentFactory singleton instance
    """
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory(
            component_factory=component_factory,
            tool_registry=tool_registry,
        )
    return _agent_factory


def reset_agent_factory() -> None:
    """Reset factory singleton (for testing)."""
    global _agent_factory
    _agent_factory = None
