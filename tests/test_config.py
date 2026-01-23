"""Tests for configuration dataclasses."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from app.config.agent_config import (
    OpenAIConfig,
    SandboxConfig,
    CacheConfig,
    OrchestratorConfig,
    AgentConfig,
)


class TestOpenAIConfig:
    """Tests for OpenAIConfig."""

    def test_create_with_required_params(self):
        """Test creating config with required parameters."""
        config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )

        assert config.api_key == "test-key"
        assert config.endpoint == "https://test.openai.azure.com"
        assert config.deployment_name == "gpt-4"
        assert config.api_version == "2024-02-15-preview"

    def test_create_with_custom_api_version(self):
        """Test creating config with custom API version."""
        config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
            api_version="2023-12-01-preview",
        )

        assert config.api_version == "2023-12-01-preview"

    def test_immutability(self):
        """Test that OpenAIConfig is immutable."""
        config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            config.api_key = "new-key"


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = SandboxConfig()

        assert config.enabled is True
        assert config.root_path == Path("./data")
        assert config.timeout == 30
        assert config.max_file_size == 10 * 1024 * 1024
        assert config.max_output_size == 1024 * 1024

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = SandboxConfig(
            enabled=False,
            root_path=Path("/custom/path"),
            timeout=60,
            max_file_size=20 * 1024 * 1024,
            max_output_size=2 * 1024 * 1024,
        )

        assert config.enabled is False
        assert config.root_path == Path("/custom/path")
        assert config.timeout == 60
        assert config.max_file_size == 20 * 1024 * 1024
        assert config.max_output_size == 2 * 1024 * 1024

    def test_immutability(self):
        """Test that SandboxConfig is immutable."""
        config = SandboxConfig()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.enabled = False


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = CacheConfig()

        assert config.enabled is True
        assert config.use_new_cache is True
        assert config.directory == "tmp/cache"
        assert config.size_limit == 500 * 1024 * 1024
        assert config.content_ttl == 0
        assert config.search_ttl == 300

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = CacheConfig(
            enabled=False,
            use_new_cache=False,
            directory="/custom/cache",
            size_limit=1024 * 1024 * 1024,
            content_ttl=600,
            search_ttl=120,
        )

        assert config.enabled is False
        assert config.use_new_cache is False
        assert config.directory == "/custom/cache"
        assert config.size_limit == 1024 * 1024 * 1024
        assert config.content_ttl == 600
        assert config.search_ttl == 120

    def test_immutability(self):
        """Test that CacheConfig is immutable."""
        config = CacheConfig()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.enabled = False


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""

    def test_create_with_defaults(self):
        """Test creating config with default values."""
        config = OrchestratorConfig()

        assert config.parallel_enabled is True
        assert config.max_concurrent_tools == 5

    def test_create_with_custom_values(self):
        """Test creating config with custom values."""
        config = OrchestratorConfig(
            parallel_enabled=False,
            max_concurrent_tools=10,
        )

        assert config.parallel_enabled is False
        assert config.max_concurrent_tools == 10

    def test_immutability(self):
        """Test that OrchestratorConfig is immutable."""
        config = OrchestratorConfig()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.parallel_enabled = False


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_create_with_required_params(self):
        """Test creating config with required parameters."""
        openai_config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )

        config = AgentConfig(openai=openai_config)

        assert config.openai == openai_config
        assert isinstance(config.sandbox, SandboxConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.orchestrator, OrchestratorConfig)
        assert config.max_tool_iterations == 10

    def test_create_with_custom_components(self):
        """Test creating config with custom component configs."""
        openai_config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )
        sandbox_config = SandboxConfig(timeout=60)
        cache_config = CacheConfig(enabled=False)
        orchestrator_config = OrchestratorConfig(parallel_enabled=False)

        config = AgentConfig(
            openai=openai_config,
            sandbox=sandbox_config,
            cache=cache_config,
            orchestrator=orchestrator_config,
            max_tool_iterations=20,
        )

        assert config.openai == openai_config
        assert config.sandbox == sandbox_config
        assert config.cache == cache_config
        assert config.orchestrator == orchestrator_config
        assert config.max_tool_iterations == 20

    def test_mutability(self):
        """Test that AgentConfig is mutable (not frozen)."""
        openai_config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )

        config = AgentConfig(openai=openai_config)

        # This should work since AgentConfig is not frozen
        config.max_tool_iterations = 20
        assert config.max_tool_iterations == 20

    def test_from_settings(self):
        """Test creating config from Settings object."""
        # Mock Settings object
        mock_settings = Mock()
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com"
        mock_settings.azure_openai_deployment_name = "gpt-4"
        mock_settings.azure_openai_api_version = "2024-02-15-preview"
        mock_settings.sandbox_enabled = True
        mock_settings.data_root_path = "./data"
        mock_settings.command_timeout = 30
        mock_settings.max_file_size = 10 * 1024 * 1024
        mock_settings.max_output_size = 1024 * 1024
        mock_settings.cache_enabled = True
        mock_settings.use_new_cache = True
        mock_settings.cache_directory = "tmp/cache"
        mock_settings.cache_size_limit = 500 * 1024 * 1024
        mock_settings.cache_content_ttl = 0.0
        mock_settings.cache_search_ttl = 300.0
        mock_settings.parallel_execution = True
        mock_settings.max_concurrent_tools = 5

        config = AgentConfig.from_settings(mock_settings)

        # Verify OpenAI config
        assert config.openai.api_key == "test-key"
        assert config.openai.endpoint == "https://test.openai.azure.com"
        assert config.openai.deployment_name == "gpt-4"
        assert config.openai.api_version == "2024-02-15-preview"

        # Verify Sandbox config
        assert config.sandbox.enabled is True
        assert config.sandbox.root_path == Path("./data")
        assert config.sandbox.timeout == 30
        assert config.sandbox.max_file_size == 10 * 1024 * 1024
        assert config.sandbox.max_output_size == 1024 * 1024

        # Verify Cache config
        assert config.cache.enabled is True
        assert config.cache.use_new_cache is True
        assert config.cache.directory == "tmp/cache"
        assert config.cache.size_limit == 500 * 1024 * 1024
        assert config.cache.content_ttl == 0
        assert config.cache.search_ttl == 300

        # Verify Orchestrator config
        assert config.orchestrator.parallel_enabled is True
        assert config.orchestrator.max_concurrent_tools == 5

    def test_from_settings_with_custom_values(self):
        """Test creating config from Settings with custom values."""
        # Mock Settings object with custom values
        mock_settings = Mock()
        mock_settings.azure_openai_api_key = "custom-key"
        mock_settings.azure_openai_endpoint = "https://custom.openai.azure.com"
        mock_settings.azure_openai_deployment_name = "gpt-4o"
        mock_settings.azure_openai_api_version = "2023-12-01-preview"
        mock_settings.sandbox_enabled = False
        mock_settings.data_root_path = "/custom/data"
        mock_settings.command_timeout = 60
        mock_settings.max_file_size = 20 * 1024 * 1024
        mock_settings.max_output_size = 2 * 1024 * 1024
        mock_settings.cache_enabled = False
        mock_settings.use_new_cache = False
        mock_settings.cache_directory = "/custom/cache"
        mock_settings.cache_size_limit = 1024 * 1024 * 1024
        mock_settings.cache_content_ttl = 600.0
        mock_settings.cache_search_ttl = 120.0
        mock_settings.parallel_execution = False
        mock_settings.max_concurrent_tools = 10

        config = AgentConfig.from_settings(mock_settings)

        # Verify custom OpenAI config
        assert config.openai.api_key == "custom-key"
        assert config.openai.endpoint == "https://custom.openai.azure.com"
        assert config.openai.deployment_name == "gpt-4o"
        assert config.openai.api_version == "2023-12-01-preview"

        # Verify custom Sandbox config
        assert config.sandbox.enabled is False
        assert config.sandbox.root_path == Path("/custom/data")
        assert config.sandbox.timeout == 60
        assert config.sandbox.max_file_size == 20 * 1024 * 1024
        assert config.sandbox.max_output_size == 2 * 1024 * 1024

        # Verify custom Cache config
        assert config.cache.enabled is False
        assert config.cache.use_new_cache is False
        assert config.cache.directory == "/custom/cache"
        assert config.cache.size_limit == 1024 * 1024 * 1024
        assert config.cache.content_ttl == 600
        assert config.cache.search_ttl == 120

        # Verify custom Orchestrator config
        assert config.orchestrator.parallel_enabled is False
        assert config.orchestrator.max_concurrent_tools == 10

    def test_from_settings_with_float_ttl(self):
        """Test that float TTL values are converted to int."""
        # Mock Settings object
        mock_settings = Mock()
        mock_settings.azure_openai_api_key = "test-key"
        mock_settings.azure_openai_endpoint = "https://test.openai.azure.com"
        mock_settings.azure_openai_deployment_name = "gpt-4"
        mock_settings.azure_openai_api_version = "2024-02-15-preview"
        mock_settings.sandbox_enabled = True
        mock_settings.data_root_path = "./data"
        mock_settings.command_timeout = 30
        mock_settings.max_file_size = 10 * 1024 * 1024
        mock_settings.max_output_size = 1024 * 1024
        mock_settings.cache_enabled = True
        mock_settings.use_new_cache = True
        mock_settings.cache_directory = "tmp/cache"
        mock_settings.cache_size_limit = 500 * 1024 * 1024
        mock_settings.cache_content_ttl = 100.5  # Float
        mock_settings.cache_search_ttl = 300.7  # Float
        mock_settings.parallel_execution = True
        mock_settings.max_concurrent_tools = 5

        config = AgentConfig.from_settings(mock_settings)

        # Verify TTL values are converted to int
        assert isinstance(config.cache.content_ttl, int)
        assert isinstance(config.cache.search_ttl, int)
        assert config.cache.content_ttl == 100
        assert config.cache.search_ttl == 300


class TestConfigIntegration:
    """Integration tests for configuration objects."""

    def test_nested_config_immutability(self):
        """Test that nested configs maintain immutability."""
        openai_config = OpenAIConfig(
            api_key="test-key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
        )

        config = AgentConfig(openai=openai_config)

        # Parent config is mutable
        config.max_tool_iterations = 20
        assert config.max_tool_iterations == 20

        # But nested configs are immutable
        with pytest.raises(Exception):  # FrozenInstanceError
            config.openai.api_key = "new-key"

        with pytest.raises(Exception):  # FrozenInstanceError
            config.sandbox.timeout = 60

        with pytest.raises(Exception):  # FrozenInstanceError
            config.cache.enabled = False

        with pytest.raises(Exception):  # FrozenInstanceError
            config.orchestrator.parallel_enabled = False

    def test_default_values_consistency(self):
        """Test that default values are consistent across configs."""
        config1 = AgentConfig(
            openai=OpenAIConfig(
                api_key="test-key",
                endpoint="https://test.openai.azure.com",
                deployment_name="gpt-4",
            )
        )

        config2 = AgentConfig(
            openai=OpenAIConfig(
                api_key="test-key",
                endpoint="https://test.openai.azure.com",
                deployment_name="gpt-4",
            )
        )

        # Default sandbox configs should have same values
        assert config1.sandbox.enabled == config2.sandbox.enabled
        assert config1.sandbox.timeout == config2.sandbox.timeout
        assert config1.sandbox.max_file_size == config2.sandbox.max_file_size
        assert config1.sandbox.max_output_size == config2.sandbox.max_output_size

        # Default cache configs should have same values
        assert config1.cache.enabled == config2.cache.enabled
        assert config1.cache.use_new_cache == config2.cache.use_new_cache
        assert config1.cache.directory == config2.cache.directory
        assert config1.cache.size_limit == config2.cache.size_limit

        # Default orchestrator configs should have same values
        assert (
            config1.orchestrator.parallel_enabled
            == config2.orchestrator.parallel_enabled
        )
        assert (
            config1.orchestrator.max_concurrent_tools
            == config2.orchestrator.max_concurrent_tools
        )
