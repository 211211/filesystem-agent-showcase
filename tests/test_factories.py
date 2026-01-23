"""
Tests for factory pattern implementation.
Tests ComponentFactory, AgentFactory, and their integrations.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from openai import AsyncAzureOpenAI

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
from app.config.agent_config import (
    OpenAIConfig,
    SandboxConfig,
    CacheConfig,
    OrchestratorConfig,
    AgentConfig,
)
from app.config import Settings
from app.sandbox.executor import SandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator
from app.cache.cache_manager import CacheManager
from app.agent.filesystem_agent import FilesystemAgent
from app.repositories.tool_registry import create_default_registry


# Fixtures

@pytest.fixture
def openai_config():
    """Create OpenAI configuration for testing."""
    return OpenAIConfig(
        api_key="test-key",
        endpoint="https://test.openai.azure.com/",
        deployment_name="gpt-4",
        api_version="2024-02-15-preview",
    )


@pytest.fixture
def sandbox_config(tmp_path):
    """Create sandbox configuration for testing."""
    return SandboxConfig(
        enabled=True,
        root_path=tmp_path,
        timeout=30,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1024 * 1024,
    )


@pytest.fixture
def cache_config():
    """Create cache configuration for testing."""
    return CacheConfig(
        enabled=True,
        use_new_cache=True,
        directory="tmp/test_cache",
        size_limit=10 * 1024 * 1024,
        content_ttl=0,
        search_ttl=300,
    )


@pytest.fixture
def orchestrator_config():
    """Create orchestrator configuration for testing."""
    return OrchestratorConfig(
        parallel_enabled=True,
        max_concurrent_tools=5,
    )


@pytest.fixture
def agent_config(openai_config, sandbox_config, cache_config, orchestrator_config):
    """Create complete agent configuration for testing."""
    return AgentConfig(
        openai=openai_config,
        sandbox=sandbox_config,
        cache=cache_config,
        orchestrator=orchestrator_config,
        max_tool_iterations=10,
    )


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.azure_openai_api_key = "test-key"
    settings.azure_openai_endpoint = "https://test.openai.azure.com/"
    settings.azure_openai_deployment_name = "gpt-4"
    settings.azure_openai_api_version = "2024-02-15-preview"
    settings.sandbox_enabled = True
    settings.data_root_path = str(tmp_path)
    settings.command_timeout = 30
    settings.max_file_size = 10 * 1024 * 1024
    settings.max_output_size = 1024 * 1024
    settings.cache_enabled = True
    settings.use_new_cache = True
    settings.cache_directory = "tmp/test_cache"
    settings.cache_size_limit = 10 * 1024 * 1024
    settings.cache_content_ttl = 0
    settings.cache_search_ttl = 300
    settings.parallel_execution = True
    settings.max_concurrent_tools = 5
    return settings


@pytest.fixture(autouse=True)
def reset_factory_singleton():
    """Reset factory singleton before each test."""
    reset_agent_factory()
    yield
    reset_agent_factory()


# DefaultComponentFactory Tests

class TestDefaultComponentFactory:
    """Test DefaultComponentFactory implementation."""

    def test_create_client(self, openai_config):
        """Test creating Azure OpenAI client."""
        factory = DefaultComponentFactory()
        client = factory.create_client(openai_config)

        assert isinstance(client, AsyncAzureOpenAI)
        # Verify configuration is applied
        # Note: AsyncAzureOpenAI doesn't expose config directly,
        # so we just check the instance type

    def test_create_executor(self, sandbox_config):
        """Test creating sandbox executor."""
        factory = DefaultComponentFactory()
        executor = factory.create_executor(sandbox_config)

        assert isinstance(executor, SandboxExecutor)
        assert executor.root_path == sandbox_config.root_path
        assert executor.timeout == sandbox_config.timeout
        assert executor.max_file_size == sandbox_config.max_file_size
        assert executor.max_output_size == sandbox_config.max_output_size
        assert executor.enabled == sandbox_config.enabled

    def test_create_cache_manager_enabled(self, cache_config):
        """Test creating cache manager when enabled."""
        factory = DefaultComponentFactory()
        cache_manager = factory.create_cache_manager(cache_config)

        assert isinstance(cache_manager, CacheManager)

    def test_create_cache_manager_disabled(self, cache_config):
        """Test cache manager returns None when disabled."""
        factory = DefaultComponentFactory()
        cache_config_disabled = CacheConfig(
            enabled=False,
            use_new_cache=True,
            directory="tmp/test_cache",
            size_limit=10 * 1024 * 1024,
            content_ttl=0,
            search_ttl=300,
        )
        cache_manager = factory.create_cache_manager(cache_config_disabled)

        assert cache_manager is None

    def test_create_cache_manager_old_cache(self, cache_config):
        """Test cache manager returns None when use_new_cache is False."""
        factory = DefaultComponentFactory()
        cache_config_old = CacheConfig(
            enabled=True,
            use_new_cache=False,
            directory="tmp/test_cache",
            size_limit=10 * 1024 * 1024,
            content_ttl=0,
            search_ttl=300,
        )
        cache_manager = factory.create_cache_manager(cache_config_old)

        assert cache_manager is None

    def test_create_orchestrator(self, orchestrator_config, sandbox_config):
        """Test creating tool orchestrator."""
        factory = DefaultComponentFactory()
        executor = factory.create_executor(sandbox_config)
        orchestrator = factory.create_orchestrator(orchestrator_config, executor)

        assert isinstance(orchestrator, ParallelToolOrchestrator)
        assert orchestrator.sandbox == executor
        assert orchestrator.max_concurrent == orchestrator_config.max_concurrent_tools


# TestComponentFactory Tests

class TestTestComponentFactory:
    """Test TestComponentFactory implementation."""

    def test_create_client_with_mock(self, openai_config):
        """Test creating client with provided mock."""
        mock_client = MagicMock(spec=AsyncAzureOpenAI)
        factory = TestComponentFactory(mock_client=mock_client)
        client = factory.create_client(openai_config)

        assert client == mock_client

    def test_create_client_without_mock(self, openai_config):
        """Test creating default mock client."""
        factory = TestComponentFactory()
        client = factory.create_client(openai_config)

        # Should be a mock with chat.completions.create method
        assert hasattr(client, "chat")
        assert hasattr(client.chat, "completions")
        assert hasattr(client.chat.completions, "create")

    def test_create_executor_with_mock(self, sandbox_config):
        """Test creating executor with provided mock."""
        mock_executor = MagicMock(spec=SandboxExecutor)
        factory = TestComponentFactory(mock_executor=mock_executor)
        executor = factory.create_executor(sandbox_config)

        assert executor == mock_executor

    def test_create_executor_without_mock(self, sandbox_config):
        """Test creating real executor for integration tests."""
        factory = TestComponentFactory()
        executor = factory.create_executor(sandbox_config)

        assert isinstance(executor, SandboxExecutor)

    def test_create_cache_manager_with_mock(self, cache_config):
        """Test creating cache manager with provided mock."""
        mock_cache = MagicMock(spec=CacheManager)
        factory = TestComponentFactory(mock_cache_manager=mock_cache)
        cache_manager = factory.create_cache_manager(cache_config)

        assert cache_manager == mock_cache

    def test_create_cache_manager_with_explicit_none(self, cache_config):
        """Test creating cache manager with explicit None mock."""
        factory = TestComponentFactory(mock_cache_manager=None)
        cache_manager = factory.create_cache_manager(cache_config)

        # Should return None when explicitly set
        assert cache_manager is None

    def test_create_cache_manager_test_config(self, cache_config):
        """Test creating test cache manager with smaller limits."""
        factory = TestComponentFactory()
        cache_manager = factory.create_cache_manager(cache_config)

        assert isinstance(cache_manager, CacheManager)
        # Test cache has smaller size limit

    def test_create_orchestrator_with_mock(self, orchestrator_config, sandbox_config):
        """Test creating orchestrator with provided mock."""
        mock_orchestrator = MagicMock(spec=ParallelToolOrchestrator)
        factory = TestComponentFactory(mock_orchestrator=mock_orchestrator)
        executor = factory.create_executor(sandbox_config)
        orchestrator = factory.create_orchestrator(orchestrator_config, executor)

        assert orchestrator == mock_orchestrator

    def test_create_orchestrator_without_mock(self, orchestrator_config, sandbox_config):
        """Test creating real orchestrator."""
        factory = TestComponentFactory()
        executor = factory.create_executor(sandbox_config)
        orchestrator = factory.create_orchestrator(orchestrator_config, executor)

        assert isinstance(orchestrator, ParallelToolOrchestrator)


# AgentFactory Tests

class TestAgentFactory:
    """Test AgentFactory implementation."""

    def test_init_default_dependencies(self):
        """Test factory initializes with default dependencies."""
        factory = AgentFactory()

        assert isinstance(factory.component_factory, DefaultComponentFactory)
        assert factory.tool_registry is not None

    def test_init_custom_dependencies(self):
        """Test factory initializes with custom dependencies."""
        custom_component_factory = TestComponentFactory()
        custom_tool_registry = create_default_registry()

        factory = AgentFactory(
            component_factory=custom_component_factory,
            tool_registry=custom_tool_registry,
        )

        assert factory.component_factory == custom_component_factory
        assert factory.tool_registry == custom_tool_registry

    def test_create_agent(self, agent_config):
        """Test creating agent from config."""
        factory = AgentFactory(component_factory=TestComponentFactory())
        agent = factory.create(agent_config)

        assert isinstance(agent, FilesystemAgent)
        assert agent.deployment_name == agent_config.openai.deployment_name
        assert agent.data_root == agent_config.sandbox.root_path
        assert agent.max_tool_iterations == agent_config.max_tool_iterations
        assert agent.parallel_execution == agent_config.orchestrator.parallel_enabled
        assert agent.max_concurrent_tools == agent_config.orchestrator.max_concurrent_tools

    def test_create_agent_with_cache(self, agent_config):
        """Test creating agent with cache enabled."""
        factory = AgentFactory(component_factory=TestComponentFactory())
        agent = factory.create(agent_config)

        # Cache should be created since config has enabled=True
        assert agent.cache_manager is not None

    def test_create_agent_without_cache(self, agent_config):
        """Test creating agent with cache disabled."""
        agent_config.cache = CacheConfig(
            enabled=False,
            use_new_cache=True,
            directory="tmp/test_cache",
            size_limit=10 * 1024 * 1024,
            content_ttl=0,
            search_ttl=300,
        )

        factory = AgentFactory(component_factory=TestComponentFactory())
        agent = factory.create(agent_config)

        assert agent.cache_manager is None

    def test_create_from_settings(self, mock_settings):
        """Test creating agent from Settings."""
        factory = AgentFactory(component_factory=TestComponentFactory())
        agent = factory.create_from_settings(mock_settings)

        assert isinstance(agent, FilesystemAgent)
        assert agent.deployment_name == mock_settings.azure_openai_deployment_name


# Singleton Tests

class TestAgentFactorySingleton:
    """Test singleton pattern for AgentFactory."""

    def test_get_agent_factory_creates_singleton(self):
        """Test get_agent_factory creates singleton."""
        factory1 = get_agent_factory()
        factory2 = get_agent_factory()

        assert factory1 is factory2

    def test_get_agent_factory_with_custom_dependencies(self):
        """Test get_agent_factory uses custom dependencies on first call."""
        custom_factory = TestComponentFactory()
        custom_registry = create_default_registry()

        factory = get_agent_factory(
            component_factory=custom_factory,
            tool_registry=custom_registry,
        )

        assert factory.component_factory == custom_factory
        assert factory.tool_registry == custom_registry

    def test_get_agent_factory_ignores_subsequent_dependencies(self):
        """Test get_agent_factory ignores dependencies on subsequent calls."""
        factory1 = get_agent_factory()
        component_factory1 = factory1.component_factory

        # Second call with different dependencies should return same factory
        custom_factory = TestComponentFactory()
        factory2 = get_agent_factory(component_factory=custom_factory)

        assert factory2 is factory1
        assert factory2.component_factory == component_factory1
        assert factory2.component_factory != custom_factory

    def test_reset_agent_factory(self):
        """Test reset_agent_factory clears singleton."""
        factory1 = get_agent_factory()
        reset_agent_factory()
        factory2 = get_agent_factory()

        assert factory1 is not factory2


# Integration Tests

class TestFactoriesIntegration:
    """Integration tests for factory pattern."""

    def test_end_to_end_agent_creation(self, mock_settings, tmp_path):
        """Test complete agent creation flow."""
        # Create test data directory
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Create factory with test components
        factory = AgentFactory(component_factory=TestComponentFactory())

        # Create agent from settings
        agent = factory.create_from_settings(mock_settings)

        assert isinstance(agent, FilesystemAgent)
        assert agent.sandbox is not None
        assert agent.cache_manager is not None

    def test_factory_with_mock_client(self, agent_config):
        """Test factory with mock OpenAI client."""
        mock_client = MagicMock(spec=AsyncAzureOpenAI)
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock()

        test_factory = TestComponentFactory(mock_client=mock_client)
        factory = AgentFactory(component_factory=test_factory)
        agent = factory.create(agent_config)

        assert agent.client == mock_client

    def test_factory_with_mock_executor(self, agent_config):
        """Test factory with mock sandbox executor."""
        mock_executor = MagicMock(spec=SandboxExecutor)

        test_factory = TestComponentFactory(mock_executor=mock_executor)
        factory = AgentFactory(component_factory=test_factory)
        agent = factory.create(agent_config)

        assert agent.sandbox == mock_executor

    def test_factory_with_all_mocks(self, agent_config):
        """Test factory with all components mocked."""
        mock_client = MagicMock(spec=AsyncAzureOpenAI)
        mock_executor = MagicMock(spec=SandboxExecutor)
        mock_cache = MagicMock(spec=CacheManager)
        mock_orchestrator = MagicMock(spec=ParallelToolOrchestrator)

        test_factory = TestComponentFactory(
            mock_client=mock_client,
            mock_executor=mock_executor,
            mock_cache_manager=mock_cache,
            mock_orchestrator=mock_orchestrator,
        )
        factory = AgentFactory(component_factory=test_factory)
        agent = factory.create(agent_config)

        assert agent.client == mock_client
        assert agent.sandbox == mock_executor
        assert agent.cache_manager == mock_cache


# Edge Cases

class TestFactoriesEdgeCases:
    """Test edge cases and error handling."""

    def test_agent_config_from_settings_creates_correct_config(self, mock_settings):
        """Test AgentConfig.from_settings creates correct configuration."""
        config = AgentConfig.from_settings(mock_settings)

        assert config.openai.api_key == mock_settings.azure_openai_api_key
        assert config.openai.endpoint == mock_settings.azure_openai_endpoint
        assert config.openai.deployment_name == mock_settings.azure_openai_deployment_name
        assert config.sandbox.enabled == mock_settings.sandbox_enabled
        assert str(config.sandbox.root_path) == mock_settings.data_root_path
        assert config.cache.enabled == mock_settings.cache_enabled
        assert config.orchestrator.parallel_enabled == mock_settings.parallel_execution

    def test_factory_creates_independent_agents(self, agent_config):
        """Test factory creates independent agent instances."""
        factory = AgentFactory(component_factory=TestComponentFactory())

        agent1 = factory.create(agent_config)
        agent2 = factory.create(agent_config)

        # Should be different instances
        assert agent1 is not agent2

    def test_component_factory_creates_independent_components(self, openai_config):
        """Test component factory creates independent components."""
        factory = DefaultComponentFactory()

        client1 = factory.create_client(openai_config)
        client2 = factory.create_client(openai_config)

        # Should be different instances
        assert client1 is not client2
