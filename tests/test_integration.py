"""
Integration tests for the Filesystem Agent Showcase.
Tests the full flow including endpoints, parallel execution, caching, and adaptive reading.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.main import app
from app.config import Settings
from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.sandbox.cached_executor import CachedSandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator, ExecutionStrategy
from app.agent.cache import ToolResultCache
from app.agent.tools.adaptive_reader import AdaptiveFileReader
from app.agent.tools.streaming import StreamingFileReader
from app.agent.filesystem_agent import FilesystemAgent, ToolCall, create_agent


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir).resolve()

        # Create test files of various sizes
        (test_dir / "small.txt").write_text("Hello, World!\nLine 2\nLine 3\n")
        (test_dir / "medium.txt").write_text("Medium file content\n" * 100)

        # Create a subdirectory with files
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("Nested content")
        (test_dir / "subdir" / "code.py").write_text("# TODO: Fix this\ndef hello():\n    pass\n")

        yield test_dir


@pytest.fixture
def sandbox(temp_data_dir):
    """Create a sandbox executor for testing."""
    return SandboxExecutor(
        root_path=temp_data_dir,
        timeout=10,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1024 * 1024,
        enabled=True,
    )


@pytest.fixture
def cached_sandbox(temp_data_dir):
    """Create a cached sandbox executor for testing."""
    return CachedSandboxExecutor(
        root_path=temp_data_dir,
        timeout=10,
        max_file_size=10 * 1024 * 1024,
        max_output_size=1024 * 1024,
        enabled=True,
        cache_enabled=True,
        cache_ttl=300,
        cache_max_size=100,
    )


@pytest.fixture
def mock_settings(temp_data_dir):
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.azure_openai_api_key = "test-key"
    settings.azure_openai_endpoint = "https://test.openai.azure.com/"
    settings.azure_openai_deployment_name = "gpt-4o"
    settings.azure_openai_api_version = "2024-02-15-preview"
    settings.data_root = temp_data_dir
    settings.data_root_path = str(temp_data_dir)
    settings.sandbox_enabled = True
    settings.command_timeout = 30
    settings.max_file_size = 10 * 1024 * 1024
    settings.max_output_size = 1024 * 1024
    settings.parallel_execution = True
    settings.max_concurrent_tools = 5
    settings.cache_enabled = True
    settings.cache_ttl = 300
    settings.cache_max_size = 100
    settings.small_file_threshold = 1_000_000
    settings.medium_file_threshold = 100_000_000
    settings.host = "0.0.0.0"
    settings.port = 8000
    settings.debug = False
    return settings


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_healthy(self, temp_data_dir, mock_settings):
        """Test that health endpoint returns healthy status."""
        with patch("app.main.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert "sandbox_enabled" in data

    @pytest.mark.asyncio
    async def test_root_endpoint(self, temp_data_dir, mock_settings):
        """Test that root endpoint returns API information."""
        with patch("app.main.get_settings", return_value=mock_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/")

                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "Filesystem Agent Showcase"
                assert "version" in data


class TestParallelToolExecution:
    """Integration tests for parallel tool execution."""

    @pytest.mark.asyncio
    async def test_orchestrator_parallel_execution(self, sandbox):
        """Test that orchestrator executes multiple tools in parallel."""
        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox,
            max_concurrent=5,
        )

        # Create multiple tool calls
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "small.txt"}),
            ToolCall(id="3", name="grep", arguments={"pattern": "TODO", "path": "."}),
        ]

        # Execute in parallel
        results = await orchestrator.execute_parallel(tool_calls)

        assert len(results) == 3
        # All results should have success status (or expected failure for grep)
        for tc, result in results:
            assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_orchestrator_analyze_dependencies(self, sandbox):
        """Test that orchestrator correctly identifies parallel-safe tools."""
        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox,
            max_concurrent=5,
        )

        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "small.txt"}),
            ToolCall(id="3", name="grep", arguments={"pattern": "Hello", "path": "small.txt"}),
        ]

        groups = orchestrator.analyze_dependencies(tool_calls)

        # All read-only tools should be in a single parallel group
        assert len(groups) == 1
        assert groups[0].strategy == ExecutionStrategy.PARALLEL
        assert len(groups[0].tools) == 3

    @pytest.mark.asyncio
    async def test_sequential_fallback_for_single_tool(self, sandbox):
        """Test that single tool call executes sequentially."""
        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox,
            max_concurrent=5,
        )

        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
        ]

        results = await orchestrator.execute_sequential(tool_calls)

        assert len(results) == 1
        tc, result = results[0]
        assert result.success


class TestCachingIntegration:
    """Integration tests for result caching."""

    @pytest.mark.asyncio
    async def test_cache_hit_on_repeated_command(self, cached_sandbox):
        """Test that repeated commands return cached results."""
        # First execution - cache miss
        result1 = await cached_sandbox.execute(["ls", "."])
        assert result1.success

        # Get initial stats
        stats1 = cached_sandbox.cache_stats()
        misses_before = stats1["misses"]

        # Second execution - should be cache hit
        result2 = await cached_sandbox.execute(["ls", "."])
        assert result2.success

        # Verify cache hit
        stats2 = cached_sandbox.cache_stats()
        assert stats2["hits"] > 0
        assert result1.stdout == result2.stdout

    @pytest.mark.asyncio
    async def test_cache_stats_tracking(self, cached_sandbox):
        """Test that cache statistics are tracked correctly."""
        # Clear any existing cache
        cached_sandbox.clear_cache()

        # Execute some commands
        await cached_sandbox.execute(["ls", "."])  # miss
        await cached_sandbox.execute(["ls", "."])  # hit
        await cached_sandbox.execute(["cat", "small.txt"])  # miss
        await cached_sandbox.execute(["cat", "small.txt"])  # hit

        stats = cached_sandbox.cache_stats()

        assert stats["size"] == 2  # Two unique commands
        assert stats["hits"] == 2
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_cache_invalidation_by_path(self, cached_sandbox, temp_data_dir):
        """Test that cache entries can be invalidated by path."""
        # Populate cache (use ./ prefix for proper path recognition)
        await cached_sandbox.execute(["cat", "./small.txt"])
        await cached_sandbox.execute(["ls", "."])

        # Verify entries are cached
        stats1 = cached_sandbox.cache_stats()
        assert stats1["size"] == 2

        # Invalidate entries for small.txt
        invalidated = cached_sandbox.invalidate_path("./small.txt")

        assert invalidated == 1

        stats2 = cached_sandbox.cache_stats()
        assert stats2["size"] == 1


class TestAdaptiveFileReading:
    """Integration tests for adaptive file reading."""

    @pytest.mark.asyncio
    async def test_small_file_full_read(self, sandbox, temp_data_dir):
        """Test that small files are read entirely."""
        reader = AdaptiveFileReader(
            sandbox=sandbox,
            small_threshold=1_000_000,  # 1MB
            medium_threshold=100_000_000,  # 100MB
        )

        result = await reader.smart_read(Path("small.txt"))

        assert result["strategy"] == "full_read"
        assert "Hello, World!" in result["content"]
        assert result["metadata"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_strategy_selection(self, sandbox):
        """Test strategy selection based on file size."""
        reader = AdaptiveFileReader(
            sandbox=sandbox,
            small_threshold=100,  # 100 bytes for testing
            medium_threshold=1000,  # 1KB for testing
        )

        # Small file strategy
        assert reader._select_strategy(50) == "full_read"

        # Medium file with query
        assert reader._select_strategy(500, query="test") == "grep"

        # Medium file without query
        assert reader._select_strategy(500) == "head_tail"

        # Large file
        assert reader._select_strategy(5000) == "head_tail"

    @pytest.mark.asyncio
    async def test_file_info_retrieval(self, sandbox, temp_data_dir):
        """Test file info retrieval with strategy recommendation."""
        reader = AdaptiveFileReader(sandbox=sandbox)

        info = await reader.get_file_info(Path("small.txt"))

        assert info["exists"] is True
        assert "size_bytes" in info
        assert "recommended_strategy" in info
        assert info["recommended_strategy"] == "full_read"


class TestStreamingFileReader:
    """Integration tests for streaming file reader."""

    @pytest.mark.asyncio
    async def test_read_chunks(self, temp_data_dir):
        """Test reading file in chunks."""
        reader = StreamingFileReader(chunk_size=10)

        file_path = temp_data_dir / "small.txt"
        chunks = []

        async for chunk in reader.read_chunks(file_path):
            chunks.append(chunk)

        combined = "".join(chunks)
        assert "Hello, World!" in combined

    @pytest.mark.asyncio
    async def test_search_in_file(self, temp_data_dir):
        """Test searching pattern in file."""
        reader = StreamingFileReader()

        file_path = temp_data_dir / "subdir" / "code.py"
        matches = await reader.search_in_large_file(
            file_path,
            pattern="TODO",
            max_matches=10,
        )

        assert len(matches) == 1
        assert matches[0]["line_number"] == 1
        assert "TODO" in matches[0]["line_content"]

    @pytest.mark.asyncio
    async def test_get_file_stats(self, temp_data_dir):
        """Test file statistics retrieval."""
        reader = StreamingFileReader()

        file_path = temp_data_dir / "small.txt"
        stats = await reader.get_file_stats(file_path)

        assert "size_bytes" in stats
        assert "line_count" in stats
        assert stats["is_binary"] is False


class TestEndToEndFlow:
    """End-to-end integration tests for the full agent flow."""

    @pytest.mark.asyncio
    async def test_agent_creation_with_all_features(self, temp_data_dir):
        """Test that agent is created with all new features enabled."""
        agent = create_agent(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4o",
            api_version="2024-02-15-preview",
            data_root=temp_data_dir,
            sandbox_enabled=True,
            command_timeout=30,
            max_file_size=10 * 1024 * 1024,
            max_output_size=1024 * 1024,
            parallel_execution=True,
            max_concurrent_tools=5,
            cache_enabled=True,
            cache_ttl=300,
            cache_max_size=100,
        )

        assert isinstance(agent, FilesystemAgent)
        assert agent.parallel_execution is True
        assert agent.max_concurrent_tools == 5
        assert agent._orchestrator is not None

    @pytest.mark.asyncio
    async def test_agent_with_caching_disabled(self, temp_data_dir):
        """Test agent creation with caching disabled."""
        agent = create_agent(
            api_key="test-key",
            endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4o",
            api_version="2024-02-15-preview",
            data_root=temp_data_dir,
            sandbox_enabled=True,
            cache_enabled=False,
        )

        assert isinstance(agent, FilesystemAgent)
        # Sandbox should be regular SandboxExecutor, not CachedSandboxExecutor
        assert isinstance(agent.sandbox, SandboxExecutor)
        assert not isinstance(agent.sandbox, CachedSandboxExecutor)

    @pytest.mark.asyncio
    async def test_agent_tool_execution(self, temp_data_dir):
        """Test that agent can execute tools correctly."""
        mock_client = AsyncMock()

        sandbox = SandboxExecutor(
            root_path=temp_data_dir,
            timeout=10,
            enabled=True,
        )

        agent = FilesystemAgent(
            client=mock_client,
            deployment_name="test-deployment",
            data_root=temp_data_dir,
            sandbox=sandbox,
            parallel_execution=True,
            max_concurrent_tools=5,
        )

        # Execute a single tool
        tc = ToolCall(id="1", name="ls", arguments={"path": "."})
        result = await agent._execute_tool(tc)

        assert result.success
        assert "small.txt" in result.stdout


class TestCacheModule:
    """Unit tests for the cache module itself."""

    def test_cache_key_generation(self):
        """Test that cache generates consistent keys."""
        cache = ToolResultCache(max_size=10, ttl_seconds=300)

        key1 = cache._generate_key(["ls", "."])
        key2 = cache._generate_key(["ls", "."])
        key3 = cache._generate_key(["ls", "/"])

        assert key1 == key2  # Same command, same key
        assert key1 != key3  # Different command, different key

    def test_cache_ttl_expiration(self):
        """Test that cached entries expire after TTL."""
        from datetime import datetime, timedelta

        cache = ToolResultCache(max_size=10, ttl_seconds=1)  # 1 second TTL

        mock_result = MagicMock()
        mock_result.success = True

        cache.set(["ls", "."], mock_result)

        # Should be found immediately
        assert cache.get(["ls", "."]) is not None

        # Manually expire the entry by modifying timestamp
        key = cache._generate_key(["ls", "."])
        cache.cache[key]["timestamp"] = datetime.now() - timedelta(seconds=10)

        # Should be expired now
        assert cache.get(["ls", "."]) is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = ToolResultCache(max_size=2, ttl_seconds=300)

        mock_result = MagicMock()
        mock_result.success = True

        # Fill cache
        cache.set(["cmd1"], mock_result)
        cache.set(["cmd2"], mock_result)

        # Access cmd1 to make it more recent
        cache.get(["cmd1"])

        # Add a third entry, should evict cmd2 (least recently used)
        cache.set(["cmd3"], mock_result)

        assert cache.get(["cmd1"]) is not None
        assert cache.get(["cmd3"]) is not None
        # cmd2 should be evicted
        stats = cache.stats()
        assert stats["size"] == 2


class TestOrchestratorModule:
    """Unit tests for the orchestrator module."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self, sandbox):
        """Test that semaphore correctly limits concurrent executions."""
        import asyncio

        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox,
            max_concurrent=2,  # Limit to 2 concurrent
        )

        # Track concurrent executions
        concurrent_count = 0
        max_concurrent = 0

        original_execute = orchestrator._execute_single_tool

        async def tracked_execute(tc):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.1)  # Simulate work
            concurrent_count -= 1
            return await original_execute(tc)

        orchestrator._execute_single_tool = tracked_execute

        # Create 5 tool calls
        tool_calls = [
            ToolCall(id=str(i), name="ls", arguments={"path": "."})
            for i in range(5)
        ]

        await orchestrator.execute_parallel(tool_calls)

        # Max concurrent should be limited by semaphore
        assert max_concurrent <= 2

    def test_unknown_tool_treated_as_sequential(self, sandbox):
        """Test that unknown tools are treated as sequential."""
        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox,
            max_concurrent=5,
        )

        tool_calls = [
            ToolCall(id="1", name="unknown_tool", arguments={}),
            ToolCall(id="2", name="ls", arguments={"path": "."}),
        ]

        groups = orchestrator.analyze_dependencies(tool_calls)

        # Should have two groups: parallel for ls, sequential for unknown
        assert len(groups) == 2

        # Find the groups
        parallel_group = next(g for g in groups if g.strategy == ExecutionStrategy.PARALLEL)
        sequential_group = next(g for g in groups if g.strategy == ExecutionStrategy.SEQUENTIAL)

        assert len(parallel_group.tools) == 1
        assert parallel_group.tools[0].name == "ls"
        assert len(sequential_group.tools) == 1
        assert sequential_group.tools[0].name == "unknown_tool"
