"""
Configuration module for the Filesystem Agent Showcase.
Uses pydantic-settings for environment variable management.
"""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Azure OpenAI Configuration
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str = "gpt-4o"
    azure_openai_api_version: str = "2024-02-15-preview"

    # Data & Sandbox Configuration
    data_root_path: str = "./data"
    sandbox_enabled: bool = True
    command_timeout: int = 30  # seconds
    max_file_size: int = 10 * 1024 * 1024  # 10MB default, in bytes
    max_output_size: int = 1024 * 1024  # 1MB for command output

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @property
    def data_root(self) -> Path:
        """Return the data root as an absolute Path."""
        return Path(self.data_root_path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
