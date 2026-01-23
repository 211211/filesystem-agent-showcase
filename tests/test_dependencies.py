"""Tests for dependency injection module.

This module tests all dependency functions including:
- Settings singleton
- SessionRepository singleton
- ToolRegistry singleton
- AgentFactory singleton
- Agent creation via factory
- reset_dependencies() clearing all singletons
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.dependencies import (
    get_settings,
    get_session_repository,
    get_tool_registry,
    get_agent_factory_dependency,
    get_agent,
    reset_dependencies,
)
from app.settings import Settings
from app.repositories.session_repository import SessionRepository
from app.repositories.tool_registry import ToolRegistry
from app.factories.agent_factory import AgentFactory
from app.agent.filesystem_agent import FilesystemAgent


class TestGetSettings:
    """Tests for get_settings() dependency."""

    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_returns_same_instance(self):
        """Test that get_settings returns the same cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_cache_cleared_by_reset(self):
        """Test that reset_dependencies clears settings cache."""
        settings1 = get_settings()
        reset_dependencies()
        settings2 = get_settings()
        # Should be different instances after reset
        assert settings1 is not settings2


class TestGetSessionRepository:
    """Tests for get_session_repository() dependency."""

    def test_get_session_repository_returns_instance(self):
        """Test that get_session_repository returns a SessionRepository."""
        reset_dependencies()  # Ensure clean state
        repo = get_session_repository()
        assert isinstance(repo, SessionRepository)

    def test_get_session_repository_returns_singleton(self):
        """Test that get_session_repository returns same instance."""
        reset_dependencies()
        repo1 = get_session_repository()
        repo2 = get_session_repository()
        assert repo1 is repo2

    def test_get_session_repository_has_default_config(self):
        """Test that repository has default TTL and max_messages."""
        reset_dependencies()
        repo = get_session_repository()
        # Create a session to verify config
        session = repo._sessions.get("test_id")
        # Since it doesn't exist, check after creating one
        import asyncio
        session = asyncio.run(repo.get_or_create("test_id"))
        assert session.max_messages == 50

    def test_get_session_repository_cleared_by_reset(self):
        """Test that reset_dependencies clears session repository."""
        reset_dependencies()
        repo1 = get_session_repository()
        reset_dependencies()
        repo2 = get_session_repository()
        assert repo1 is not repo2


class TestGetToolRegistry:
    """Tests for get_tool_registry() dependency."""

    def test_get_tool_registry_returns_instance(self):
        """Test that get_tool_registry returns a ToolRegistry."""
        reset_dependencies()
        registry = get_tool_registry()
        assert isinstance(registry, ToolRegistry)

    def test_get_tool_registry_returns_singleton(self):
        """Test that get_tool_registry returns same instance."""
        reset_dependencies()
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2

    def test_get_tool_registry_has_default_tools(self):
        """Test that registry has default bash tools registered."""
        reset_dependencies()
        registry = get_tool_registry()
        expected_tools = ["grep", "find", "cat", "head", "tail", "ls", "wc"]
        registered_tools = registry.list_names()

        for tool in expected_tools:
            assert tool in registered_tools, f"Tool {tool} not registered"

    def test_get_tool_registry_cleared_by_reset(self):
        """Test that reset_dependencies clears tool registry."""
        reset_dependencies()
        registry1 = get_tool_registry()
        reset_dependencies()
        registry2 = get_tool_registry()
        assert registry1 is not registry2


class TestGetAgentFactory:
    """Tests for get_agent_factory_dependency() dependency."""

    def test_get_agent_factory_returns_instance(self):
        """Test that get_agent_factory returns an AgentFactory."""
        reset_dependencies()
        factory = get_agent_factory_dependency()
        assert isinstance(factory, AgentFactory)

    def test_get_agent_factory_returns_singleton(self):
        """Test that get_agent_factory returns same instance."""
        reset_dependencies()
        factory1 = get_agent_factory_dependency()
        factory2 = get_agent_factory_dependency()
        assert factory1 is factory2

    def test_get_agent_factory_cleared_by_reset(self):
        """Test that reset_dependencies clears agent factory."""
        reset_dependencies()
        factory1 = get_agent_factory_dependency()
        reset_dependencies()
        factory2 = get_agent_factory_dependency()
        assert factory1 is not factory2


class TestGetAgent:
    """Tests for get_agent() dependency."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings for testing."""
        # Use environment variables or create minimal settings
        with patch.dict('os.environ', {
            'AZURE_OPENAI_API_KEY': 'test-key',
            'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com',
            'AZURE_OPENAI_DEPLOYMENT_NAME': 'gpt-4',
            'AZURE_OPENAI_API_VERSION': '2024-02-15-preview',
            'DATA_ROOT_PATH': str(tmp_path / "data"),
        }):
            yield Settings()

    def test_get_agent_returns_filesystem_agent(self, mock_settings):
        """Test that get_agent returns a FilesystemAgent instance."""
        reset_dependencies()
        agent = get_agent(settings=mock_settings)
        assert isinstance(agent, FilesystemAgent)

    def test_get_agent_uses_default_settings_if_not_provided(self):
        """Test that get_agent uses get_settings() if no settings provided."""
        reset_dependencies()

        # Mock get_settings to return a mock settings
        with patch('app.dependencies.get_settings') as mock_get_settings:
            mock_settings = MagicMock(spec=Settings)
            mock_settings.azure_openai_api_key = "test-key"
            mock_settings.azure_openai_endpoint = "https://test.openai.azure.com"
            mock_settings.azure_openai_deployment_name = "gpt-4"
            mock_settings.azure_openai_api_version = "2024-02-15-preview"
            mock_settings.data_root = Path("data")
            mock_settings.data_root_path = "data"  # Add this for AgentConfig
            mock_settings.sandbox_enabled = True
            mock_settings.command_timeout = 30
            mock_settings.max_file_size = 1048576
            mock_settings.max_output_size = 1048576
            mock_settings.parallel_execution = True
            mock_settings.max_concurrent_tools = 5
            mock_settings.cache_enabled = True
            mock_settings.cache_ttl = 300
            mock_settings.cache_max_size = 1000
            mock_settings.use_new_cache = False
            mock_settings.cache_directory = Path("tmp/cache")
            mock_settings.cache_size_limit = 500 * 1024 * 1024
            mock_settings.cache_content_ttl = 0
            mock_settings.cache_search_ttl = 300

            mock_get_settings.return_value = mock_settings

            # This should call get_settings internally
            agent = get_agent()

            # Verify get_settings was called
            mock_get_settings.assert_called_once()
            assert isinstance(agent, FilesystemAgent)

    def test_get_agent_creates_new_instance_each_call(self, mock_settings):
        """Test that get_agent creates a new agent instance on each call."""
        reset_dependencies()
        agent1 = get_agent(settings=mock_settings)
        agent2 = get_agent(settings=mock_settings)

        # Should be different instances
        assert agent1 is not agent2

    def test_get_agent_uses_factory(self, mock_settings):
        """Test that get_agent uses the factory to create agents."""
        reset_dependencies()

        with patch('app.dependencies.get_agent_factory_dependency') as mock_factory_getter:
            mock_factory = MagicMock(spec=AgentFactory)
            mock_agent = MagicMock(spec=FilesystemAgent)
            mock_factory.create_from_settings.return_value = mock_agent
            mock_factory_getter.return_value = mock_factory

            agent = get_agent(settings=mock_settings)

            # Verify factory was used
            mock_factory_getter.assert_called_once()
            mock_factory.create_from_settings.assert_called_once_with(mock_settings)
            assert agent is mock_agent


class TestResetDependencies:
    """Tests for reset_dependencies() function."""

    def test_reset_dependencies_clears_all_singletons(self):
        """Test that reset_dependencies clears all singleton instances."""
        # Initialize all singletons
        settings1 = get_settings()
        repo1 = get_session_repository()
        registry1 = get_tool_registry()
        factory1 = get_agent_factory_dependency()

        # Reset all dependencies
        reset_dependencies()

        # Get new instances
        settings2 = get_settings()
        repo2 = get_session_repository()
        registry2 = get_tool_registry()
        factory2 = get_agent_factory_dependency()

        # All should be new instances
        assert settings1 is not settings2
        assert repo1 is not repo2
        assert registry1 is not registry2
        assert factory1 is not factory2

    def test_reset_dependencies_can_be_called_multiple_times(self):
        """Test that reset_dependencies can be called multiple times safely."""
        reset_dependencies()
        reset_dependencies()  # Should not raise any errors
        reset_dependencies()

        # Verify we can still get dependencies
        settings = get_settings()
        repo = get_session_repository()
        registry = get_tool_registry()
        factory = get_agent_factory_dependency()

        assert settings is not None
        assert repo is not None
        assert registry is not None
        assert factory is not None

    def test_reset_dependencies_idempotent(self):
        """Test that calling reset multiple times has same effect."""
        # Initialize singletons
        get_settings()
        get_session_repository()
        get_tool_registry()
        get_agent_factory_dependency()

        # First reset
        reset_dependencies()
        settings1 = get_settings()
        repo1 = get_session_repository()

        # Second reset
        reset_dependencies()
        settings2 = get_settings()
        repo2 = get_session_repository()

        # Both should be different from each other
        assert settings1 is not settings2
        assert repo1 is not repo2


class TestDependencyIntegration:
    """Integration tests for dependency injection system."""

    def test_all_dependencies_work_together(self, tmp_path):
        """Test that all dependencies can be used together."""
        reset_dependencies()

        # Create test environment
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "test.txt").write_text("test content")

        with patch.dict('os.environ', {
            'AZURE_OPENAI_API_KEY': 'test-key',
            'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com',
            'AZURE_OPENAI_DEPLOYMENT_NAME': 'gpt-4',
            'AZURE_OPENAI_API_VERSION': '2024-02-15-preview',
            'DATA_ROOT_PATH': str(data_dir),
        }):
            # Get all dependencies
            settings = get_settings()
            repo = get_session_repository()
            registry = get_tool_registry()
            factory = get_agent_factory_dependency()
            agent = get_agent(settings=settings)

            # Verify all are valid instances
            assert isinstance(settings, Settings)
            assert isinstance(repo, SessionRepository)
            assert isinstance(registry, ToolRegistry)
            assert isinstance(factory, AgentFactory)
            assert isinstance(agent, FilesystemAgent)

    def test_dependencies_persist_across_calls(self):
        """Test that singletons persist across multiple calls."""
        reset_dependencies()

        # Call dependencies multiple times
        settings_calls = [get_settings() for _ in range(5)]
        repo_calls = [get_session_repository() for _ in range(5)]
        registry_calls = [get_tool_registry() for _ in range(5)]
        factory_calls = [get_agent_factory_dependency() for _ in range(5)]

        # All should be the same instance
        assert all(s is settings_calls[0] for s in settings_calls)
        assert all(r is repo_calls[0] for r in repo_calls)
        assert all(r is registry_calls[0] for r in registry_calls)
        assert all(f is factory_calls[0] for f in factory_calls)

    def test_agent_creation_uses_correct_settings(self, tmp_path):
        """Test that agent is created with correct settings from factory."""
        reset_dependencies()

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch.dict('os.environ', {
            'AZURE_OPENAI_API_KEY': 'test-key',
            'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com',
            'AZURE_OPENAI_DEPLOYMENT_NAME': 'gpt-4',
            'AZURE_OPENAI_API_VERSION': '2024-02-15-preview',
            'DATA_ROOT_PATH': str(data_dir),
            'PARALLEL_EXECUTION': 'true',
            'MAX_CONCURRENT_TOOLS': '3',
        }):
            settings = get_settings()
            agent = get_agent(settings=settings)

            # Verify agent has correct configuration
            assert agent.data_root == data_dir
            assert agent.parallel_execution is True
            assert agent.max_concurrent_tools == 3


class TestFastAPIIntegration:
    """Tests for FastAPI Depends() integration."""

    def test_get_agent_compatible_with_depends(self):
        """Test that get_agent() can be used with FastAPI Depends()."""
        from fastapi import Depends

        # This should not raise any errors
        def example_route(agent: FilesystemAgent = Depends(get_agent)):
            return agent

        # Verify function signature is correct
        import inspect
        sig = inspect.signature(example_route)
        assert 'agent' in sig.parameters
        assert sig.parameters['agent'].annotation == FilesystemAgent

    def test_dependencies_can_be_injected_together(self):
        """Test that multiple dependencies can be injected together."""
        from fastapi import Depends

        def example_route(
            agent: FilesystemAgent = Depends(get_agent),
            settings: Settings = Depends(get_settings),
            repo: SessionRepository = Depends(get_session_repository),
        ):
            return {"agent": agent, "settings": settings, "repo": repo}

        # Verify all parameters are present
        import inspect
        sig = inspect.signature(example_route)
        assert 'agent' in sig.parameters
        assert 'settings' in sig.parameters
        assert 'repo' in sig.parameters
