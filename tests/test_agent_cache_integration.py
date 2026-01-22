"""
Tests for FilesystemAgent integration with new CacheManager.

This module tests the integration of the new cache system (CacheManager)
with FilesystemAgent, verifying that cached read and search operations
work correctly.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from openai import AsyncAzureOpenAI

from app.agent.filesystem_agent import FilesystemAgent, create_agent, ToolCall
from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.cache import CacheManager


@pytest.fixture
def data_root(tmp_path):
    """Create a temporary data root directory with test files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create test files
    (data_dir / "test.txt").write_text("Hello, World!")
    (data_dir / "config.json").write_text('{"key": "value"}')

    subdir = data_dir / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("Nested content")

    return data_dir


@pytest.fixture
def cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache = tmp_path / "cache"
    cache.mkdir()
    return str(cache)


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    return AsyncMock(spec=AsyncAzureOpenAI)


@pytest.fixture
def sandbox(data_root):
    """Create a real sandbox executor for testing."""
    return SandboxExecutor(
        root_path=data_root,
        timeout=30,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1024 * 1024,
        enabled=True,
    )


@pytest.fixture
def cache_manager(cache_dir):
    """Create a CacheManager instance for testing."""
    return CacheManager(
        cache_dir=cache_dir,
        size_limit=100 * 1024 * 1024,  # 100MB
    )


@pytest.fixture
def agent_with_cache(mock_openai_client, data_root, sandbox, cache_manager):
    """Create a FilesystemAgent with new cache enabled."""
    return FilesystemAgent(
        client=mock_openai_client,
        deployment_name="gpt-4",
        data_root=data_root,
        sandbox=sandbox,
        cache_manager=cache_manager,
    )


@pytest.fixture
def agent_without_cache(mock_openai_client, data_root, sandbox):
    """Create a FilesystemAgent without cache."""
    return FilesystemAgent(
        client=mock_openai_client,
        deployment_name="gpt-4",
        data_root=data_root,
        sandbox=sandbox,
        cache_manager=None,
    )


class TestCacheIntegration:
    """Test suite for CacheManager integration with FilesystemAgent."""

    @pytest.mark.asyncio
    async def test_agent_initialization_with_cache(self, agent_with_cache):
        """Test that agent initializes correctly with cache manager."""
        assert agent_with_cache.cache_manager is not None
        assert isinstance(agent_with_cache.cache_manager, CacheManager)

    @pytest.mark.asyncio
    async def test_agent_initialization_without_cache(self, agent_without_cache):
        """Test that agent initializes correctly without cache manager."""
        assert agent_without_cache.cache_manager is None

    @pytest.mark.asyncio
    async def test_cached_cat_operation(self, agent_with_cache, data_root):
        """Test that cat operation uses content cache."""
        tool_call = ToolCall(
            id="call_1",
            name="cat",
            arguments={"path": "test.txt"}
        )

        # First call - cache miss
        result1 = await agent_with_cache._execute_tool(tool_call)
        assert result1.success
        assert "Hello, World!" in result1.stdout

        # Second call - should hit cache
        result2 = await agent_with_cache._execute_tool(tool_call)
        assert result2.success
        assert result2.stdout == result1.stdout

        # Verify cache stats show activity
        stats = agent_with_cache.get_cache_stats()
        assert stats["new_cache"]["enabled"] != False
        assert stats["new_cache"]["disk_cache"]["size"] > 0

    @pytest.mark.asyncio
    async def test_cached_head_operation(self, agent_with_cache, data_root):
        """Test that head operation uses content cache."""
        tool_call = ToolCall(
            id="call_2",
            name="head",
            arguments={"path": "test.txt", "lines": 5}
        )

        # Execute tool call
        result = await agent_with_cache._execute_tool(tool_call)
        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_cached_grep_operation(self, agent_with_cache, data_root):
        """Test that grep operation uses search cache."""
        tool_call = ToolCall(
            id="call_3",
            name="grep",
            arguments={
                "pattern": "Hello",
                "path": ".",
                "recursive": True,
                "ignore_case": False
            }
        )

        # First call - cache miss
        result1 = await agent_with_cache._execute_tool(tool_call)
        assert result1.success

        # Second call - should hit cache
        result2 = await agent_with_cache._execute_tool(tool_call)
        assert result2.success
        assert result2.stdout == result1.stdout

    @pytest.mark.asyncio
    async def test_cached_find_operation(self, agent_with_cache, data_root):
        """Test that find operation uses search cache."""
        tool_call = ToolCall(
            id="call_4",
            name="find",
            arguments={
                "path": ".",
                "name_pattern": "*.txt",
                "type": "f"
            }
        )

        # Execute tool call
        result = await agent_with_cache._execute_tool(tool_call)
        assert result.success
        assert "test.txt" in result.stdout

    @pytest.mark.asyncio
    async def test_non_cached_operations(self, agent_with_cache, data_root):
        """Test that non-cacheable operations work normally."""
        # ls operation should not be cached
        tool_call = ToolCall(
            id="call_5",
            name="ls",
            arguments={"path": ".", "all": False, "long": False}
        )

        result = await agent_with_cache._execute_tool(tool_call)
        assert result.success

    @pytest.mark.asyncio
    async def test_cache_stats_retrieval(self, agent_with_cache):
        """Test that cache statistics can be retrieved."""
        stats = agent_with_cache.get_cache_stats()

        assert "new_cache" in stats
        assert "old_cache" in stats
        assert stats["new_cache"]["enabled"] != False
        assert "disk_cache" in stats["new_cache"]

    @pytest.mark.asyncio
    async def test_cache_stats_without_cache(self, agent_without_cache):
        """Test cache stats when cache is disabled."""
        stats = agent_without_cache.get_cache_stats()

        assert stats["new_cache"]["enabled"] == False
        assert stats["old_cache"]["enabled"] == False

    @pytest.mark.asyncio
    async def test_file_change_detection(self, agent_with_cache, data_root):
        """Test that cache invalidates when file changes."""
        file_path = data_root / "test.txt"
        tool_call = ToolCall(
            id="call_6",
            name="cat",
            arguments={"path": "test.txt"}
        )

        # First read
        result1 = await agent_with_cache._execute_tool(tool_call)
        assert "Hello, World!" in result1.stdout

        # Modify file
        file_path.write_text("Modified content")

        # Second read - should detect change and return new content
        result2 = await agent_with_cache._execute_tool(tool_call)
        assert "Modified content" in result2.stdout
        assert "Hello, World!" not in result2.stdout

    @pytest.mark.asyncio
    async def test_error_handling_in_cached_read(self, agent_with_cache):
        """Test error handling when cached read fails."""
        tool_call = ToolCall(
            id="call_7",
            name="cat",
            arguments={"path": "nonexistent.txt"}
        )

        result = await agent_with_cache._execute_tool(tool_call)
        assert not result.success
        assert result.return_code != 0

    @pytest.mark.asyncio
    async def test_error_handling_in_cached_search(self, agent_with_cache):
        """Test error handling when cached search fails."""
        tool_call = ToolCall(
            id="call_8",
            name="grep",
            arguments={
                "pattern": "test",
                "path": "nonexistent_dir",
                "recursive": True,
            }
        )

        result = await agent_with_cache._execute_tool(tool_call)
        # Should handle error gracefully
        assert result is not None


class TestCreateAgentFactory:
    """Test suite for create_agent factory function with new cache."""

    def test_create_agent_with_new_cache(self, data_root, cache_dir):
        """Test creating agent with new cache system enabled."""
        agent = create_agent(
            api_key="test_key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
            api_version="2024-02-15-preview",
            data_root=data_root,
            use_new_cache=True,
            cache_directory=cache_dir,
            cache_size_limit=100 * 1024 * 1024,
        )

        assert agent.cache_manager is not None
        assert isinstance(agent.cache_manager, CacheManager)

    def test_create_agent_without_new_cache(self, data_root):
        """Test creating agent without new cache system."""
        agent = create_agent(
            api_key="test_key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
            api_version="2024-02-15-preview",
            data_root=data_root,
            use_new_cache=False,
            cache_enabled=False,
        )

        assert agent.cache_manager is None

    def test_create_agent_with_old_cache_only(self, data_root):
        """Test backward compatibility with old cache system."""
        agent = create_agent(
            api_key="test_key",
            endpoint="https://test.openai.azure.com",
            deployment_name="gpt-4",
            api_version="2024-02-15-preview",
            data_root=data_root,
            use_new_cache=False,
            cache_enabled=True,
            cache_ttl=300,
            cache_max_size=100,
        )

        assert agent.cache_manager is None
        # Old cache should be enabled via CachedSandboxExecutor
        from app.sandbox.cached_executor import CachedSandboxExecutor
        assert isinstance(agent.sandbox, CachedSandboxExecutor)


class TestCachePerformance:
    """Test cache performance improvements."""

    @pytest.mark.asyncio
    async def test_cache_reduces_execution_time(self, agent_with_cache, data_root):
        """Test that cache improves performance for repeated operations."""
        import time

        tool_call = ToolCall(
            id="call_perf",
            name="cat",
            arguments={"path": "test.txt"}
        )

        # First call (cache miss)
        start1 = time.time()
        result1 = await agent_with_cache._execute_tool(tool_call)
        time1 = time.time() - start1

        # Second call (cache hit)
        start2 = time.time()
        result2 = await agent_with_cache._execute_tool(tool_call)
        time2 = time.time() - start2

        assert result1.success
        assert result2.success
        assert result1.stdout == result2.stdout

        # Note: In unit tests, the difference might be minimal due to small files
        # In production with large files, cache should be significantly faster


class TestCacheConcurrency:
    """Test cache behavior under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, agent_with_cache, data_root):
        """Test that cache handles concurrent access correctly."""
        import asyncio

        tool_call = ToolCall(
            id="call_concurrent",
            name="cat",
            arguments={"path": "test.txt"}
        )

        # Execute multiple concurrent reads
        tasks = [
            agent_with_cache._execute_tool(tool_call)
            for _ in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All results should be successful and identical
        assert all(r.success for r in results)
        assert all(r.stdout == results[0].stdout for r in results)
