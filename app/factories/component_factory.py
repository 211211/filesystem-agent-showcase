"""
Component Factory for creating agent dependencies.
Provides abstract factory pattern for dependency injection and testing.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Union, cast

from openai import AsyncAzureOpenAI

from app.config.agent_config import (
    OpenAIConfig,
    SandboxConfig,
    CacheConfig,
    OrchestratorConfig,
)
from app.sandbox.executor import SandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator
from app.cache.cache_manager import CacheManager
from app.interfaces.executor import IExecutor
from app.interfaces.cache import ICacheManager
from app.interfaces.orchestrator import IToolOrchestrator

# Sentinel value to distinguish between "not provided" and "explicitly None"
_NOT_PROVIDED = object()


class ComponentFactory(ABC):
    """Abstract factory for creating agent components."""

    @abstractmethod
    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        """
        Create Azure OpenAI client.

        Args:
            config: OpenAI configuration

        Returns:
            Configured AsyncAzureOpenAI client
        """
        pass

    @abstractmethod
    def create_executor(self, config: SandboxConfig) -> IExecutor:
        """
        Create sandbox executor.

        Args:
            config: Sandbox configuration

        Returns:
            Configured executor implementing IExecutor
        """
        pass

    @abstractmethod
    def create_cache_manager(self, config: CacheConfig) -> Optional[ICacheManager]:
        """
        Create cache manager (None if disabled).

        Args:
            config: Cache configuration

        Returns:
            CacheManager implementing ICacheManager if enabled, None otherwise
        """
        pass

    @abstractmethod
    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: IExecutor,
    ) -> IToolOrchestrator:
        """
        Create tool orchestrator.

        Args:
            config: Orchestrator configuration
            executor: Executor implementing IExecutor

        Returns:
            Configured orchestrator implementing IToolOrchestrator
        """
        pass


class DefaultComponentFactory(ComponentFactory):
    """Default factory implementation for production use."""

    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        """Create production Azure OpenAI client."""
        return AsyncAzureOpenAI(
            api_key=config.api_key,
            azure_endpoint=config.endpoint,
            api_version=config.api_version,
        )

    def create_executor(self, config: SandboxConfig) -> IExecutor:
        """Create production sandbox executor."""
        return SandboxExecutor(
            root_path=config.root_path,
            timeout=config.timeout,
            max_file_size=config.max_file_size,
            max_output_size=config.max_output_size,
            enabled=config.enabled,
        )

    def create_cache_manager(self, config: CacheConfig) -> Optional[ICacheManager]:
        """Create cache manager if enabled."""
        if not config.enabled:
            return None

        if config.use_new_cache:
            return CacheManager(
                cache_dir=config.directory,
                size_limit=config.size_limit,
                content_ttl=config.content_ttl,
                search_ttl=config.search_ttl,
            )
        return None

    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: IExecutor,
    ) -> IToolOrchestrator:
        """Create production tool orchestrator."""
        return ParallelToolOrchestrator(
            sandbox=executor,
            max_concurrent=config.max_concurrent_tools,
        )


class MockComponentFactory(ComponentFactory):
    """Factory for testing with mock components."""

    # Sentinel type alias for better type hints
    _SentinelOrClient = Union[object, AsyncAzureOpenAI, None]
    _SentinelOrExecutor = Union[object, IExecutor, None]
    _SentinelOrCacheManager = Union[object, ICacheManager, None]
    _SentinelOrOrchestrator = Union[object, IToolOrchestrator, None]

    def __init__(
        self,
        mock_client: _SentinelOrClient = _NOT_PROVIDED,
        mock_executor: _SentinelOrExecutor = _NOT_PROVIDED,
        mock_cache_manager: _SentinelOrCacheManager = _NOT_PROVIDED,
        mock_orchestrator: _SentinelOrOrchestrator = _NOT_PROVIDED,
    ):
        """
        Initialize test factory with optional mocks.

        Args:
            mock_client: Mock AsyncAzureOpenAI client (or None to disable)
            mock_executor: Mock SandboxExecutor (or None to disable)
            mock_cache_manager: Mock CacheManager (or None to disable, default creates real cache)
            mock_orchestrator: Mock ParallelToolOrchestrator (or None to disable)
        """
        self.mock_client: MockComponentFactory._SentinelOrClient = mock_client
        self.mock_executor: MockComponentFactory._SentinelOrExecutor = mock_executor
        self.mock_cache_manager: MockComponentFactory._SentinelOrCacheManager = (
            mock_cache_manager
        )
        self.mock_orchestrator: MockComponentFactory._SentinelOrOrchestrator = (
            mock_orchestrator
        )

    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        """Create mock or real Azure OpenAI client."""
        if self.mock_client is not _NOT_PROVIDED:
            return cast(AsyncAzureOpenAI, self.mock_client)

        # Return a mock that can be used in tests
        from unittest.mock import AsyncMock, MagicMock

        mock = MagicMock(spec=AsyncAzureOpenAI)
        mock.chat = MagicMock()
        mock.chat.completions = MagicMock()
        mock.chat.completions.create = AsyncMock()
        return cast(AsyncAzureOpenAI, mock)

    def create_executor(self, config: SandboxConfig) -> IExecutor:
        """Create mock or real sandbox executor."""
        if self.mock_executor is not _NOT_PROVIDED:
            return cast(IExecutor, self.mock_executor)

        # Return real executor for integration tests
        return SandboxExecutor(
            root_path=config.root_path,
            timeout=config.timeout,
            max_file_size=config.max_file_size,
            max_output_size=config.max_output_size,
            enabled=config.enabled,
        )

    def create_cache_manager(self, config: CacheConfig) -> Optional[ICacheManager]:
        """Create mock or test cache manager."""
        if self.mock_cache_manager is not _NOT_PROVIDED:
            # Return the mock even if it's explicitly None
            return cast(Optional[ICacheManager], self.mock_cache_manager)

        if not config.enabled:
            return None

        # Use in-memory cache for tests with smaller limits
        return CacheManager(
            cache_dir="tmp/test_cache",
            size_limit=10 * 1024 * 1024,  # 10MB for tests
            content_ttl=config.content_ttl,
            search_ttl=config.search_ttl,
        )

    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: IExecutor,
    ) -> IToolOrchestrator:
        """Create mock or real tool orchestrator."""
        if self.mock_orchestrator is not _NOT_PROVIDED:
            return cast(IToolOrchestrator, self.mock_orchestrator)

        return ParallelToolOrchestrator(
            sandbox=executor,
            max_concurrent=config.max_concurrent_tools,
        )
