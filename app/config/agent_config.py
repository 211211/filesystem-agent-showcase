"""
Configuration dataclasses for agent components.
Provides immutable configuration objects for dependency injection.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.settings import Settings


@dataclass(frozen=True)
class OpenAIConfig:
    """Azure OpenAI configuration."""

    api_key: str
    endpoint: str
    deployment_name: str
    api_version: str = "2024-02-15-preview"


@dataclass(frozen=True)
class SandboxConfig:
    """Sandbox execution configuration."""

    enabled: bool = True
    root_path: Path = field(default_factory=lambda: Path("./data"))
    timeout: int = 30
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_output_size: int = 1024 * 1024  # 1MB


@dataclass(frozen=True)
class CacheConfig:
    """Cache system configuration."""

    enabled: bool = True
    use_new_cache: bool = True
    directory: str = "tmp/cache"
    size_limit: int = 500 * 1024 * 1024  # 500MB
    content_ttl: int = 0
    search_ttl: int = 300


@dataclass(frozen=True)
class OrchestratorConfig:
    """Tool orchestration configuration."""

    parallel_enabled: bool = True
    max_concurrent_tools: int = 5


@dataclass
class AgentConfig:
    """Complete agent configuration."""

    openai: OpenAIConfig
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    max_tool_iterations: int = 10

    @classmethod
    def from_settings(cls, settings: "Settings") -> "AgentConfig":
        """Create config from application settings."""
        return cls(
            openai=OpenAIConfig(
                api_key=settings.azure_openai_api_key,
                endpoint=settings.azure_openai_endpoint,
                deployment_name=settings.azure_openai_deployment_name,
                api_version=settings.azure_openai_api_version,
            ),
            sandbox=SandboxConfig(
                enabled=settings.sandbox_enabled,
                root_path=Path(settings.data_root_path),
                timeout=settings.command_timeout,
                max_file_size=settings.max_file_size,
                max_output_size=settings.max_output_size,
            ),
            cache=CacheConfig(
                enabled=settings.cache_enabled,
                use_new_cache=settings.use_new_cache,
                directory=settings.cache_directory,
                size_limit=settings.cache_size_limit,
                content_ttl=int(settings.cache_content_ttl),
                search_ttl=int(settings.cache_search_ttl),
            ),
            orchestrator=OrchestratorConfig(
                parallel_enabled=settings.parallel_execution,
                max_concurrent_tools=settings.max_concurrent_tools,
            ),
        )
