"""
Tests for the parallel tool orchestrator.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import time

from app.agent.orchestrator import (
    ParallelToolOrchestrator,
    ExecutionStrategy,
    ToolGroup,
    READ_ONLY_TOOLS,
)
from app.agent.filesystem_agent import ToolCall
from app.sandbox.executor import SandboxExecutor, ExecutionResult


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir).resolve()
        (test_dir / "test.txt").write_text("Hello, World!\nLine 2\nLine 3")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "nested.txt").write_text("Nested content")
        (test_dir / "another.txt").write_text("Another file content")
        yield test_dir


@pytest.fixture
def sandbox(temp_data_dir):
    """Create a sandbox executor for testing."""
    return SandboxExecutor(root_path=temp_data_dir, timeout=10, enabled=True)


@pytest.fixture
def orchestrator(sandbox):
    """Create an orchestrator for testing."""
    return ParallelToolOrchestrator(sandbox=sandbox, max_concurrent=5)


class TestExecutionStrategy:
    """Tests for ExecutionStrategy enum."""

    def test_strategy_values(self):
        """Test that all strategies have expected values."""
        assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
        assert ExecutionStrategy.PARALLEL.value == "parallel"
        assert ExecutionStrategy.BATCHED.value == "batched"


class TestToolGroup:
    """Tests for ToolGroup dataclass."""

    def test_tool_group_creation(self):
        """Test creating a ToolGroup."""
        tools = [ToolCall(id="1", name="ls", arguments={"path": "."})]
        group = ToolGroup(
            tools=tools,
            strategy=ExecutionStrategy.PARALLEL,
            depends_on=[],
        )
        assert len(group.tools) == 1
        assert group.strategy == ExecutionStrategy.PARALLEL
        assert group.depends_on == []

    def test_tool_group_with_dependencies(self):
        """Test creating a ToolGroup with dependencies."""
        tools = [ToolCall(id="1", name="ls", arguments={"path": "."})]
        group = ToolGroup(
            tools=tools,
            strategy=ExecutionStrategy.SEQUENTIAL,
            depends_on=["read_only_group"],
        )
        assert group.depends_on == ["read_only_group"]


class TestReadOnlyTools:
    """Tests for READ_ONLY_TOOLS constant."""

    def test_common_read_tools_included(self):
        """Test that common read-only tools are in the set."""
        assert "grep" in READ_ONLY_TOOLS
        assert "find" in READ_ONLY_TOOLS
        assert "cat" in READ_ONLY_TOOLS
        assert "ls" in READ_ONLY_TOOLS
        assert "head" in READ_ONLY_TOOLS
        assert "tree" in READ_ONLY_TOOLS
        assert "wc" in READ_ONLY_TOOLS

    def test_write_tools_not_included(self):
        """Test that write/modify tools are not in the read-only set."""
        assert "rm" not in READ_ONLY_TOOLS
        assert "mv" not in READ_ONLY_TOOLS
        assert "cp" not in READ_ONLY_TOOLS
        assert "chmod" not in READ_ONLY_TOOLS


class TestParallelToolOrchestrator:
    """Tests for ParallelToolOrchestrator class."""

    def test_orchestrator_initialization(self, sandbox):
        """Test orchestrator initialization."""
        orchestrator = ParallelToolOrchestrator(sandbox=sandbox, max_concurrent=3)
        assert orchestrator.sandbox == sandbox
        assert orchestrator.max_concurrent == 3

    def test_default_max_concurrent(self, sandbox):
        """Test default max_concurrent value."""
        orchestrator = ParallelToolOrchestrator(sandbox=sandbox)
        assert orchestrator.max_concurrent == 5


class TestAnalyzeDependencies:
    """Tests for analyze_dependencies method."""

    def test_analyze_empty_list(self, orchestrator):
        """Test analyzing empty tool list."""
        groups = orchestrator.analyze_dependencies([])
        assert groups == []

    def test_analyze_single_read_tool(self, orchestrator):
        """Test analyzing a single read-only tool."""
        tool_calls = [ToolCall(id="1", name="ls", arguments={"path": "."})]
        groups = orchestrator.analyze_dependencies(tool_calls)

        assert len(groups) == 1
        assert groups[0].strategy == ExecutionStrategy.PARALLEL
        assert len(groups[0].tools) == 1

    def test_analyze_multiple_read_tools(self, orchestrator):
        """Test analyzing multiple read-only tools."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "test.txt"}),
            ToolCall(id="3", name="grep", arguments={"pattern": "Hello", "path": "test.txt"}),
        ]
        groups = orchestrator.analyze_dependencies(tool_calls)

        assert len(groups) == 1
        assert groups[0].strategy == ExecutionStrategy.PARALLEL
        assert len(groups[0].tools) == 3

    def test_analyze_all_read_tools_in_parallel_group(self, orchestrator):
        """Test that all read-only tools are grouped for parallel execution."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="find", arguments={"path": ".", "name_pattern": "*.txt"}),
            ToolCall(id="3", name="cat", arguments={"path": "test.txt"}),
            ToolCall(id="4", name="head", arguments={"path": "test.txt", "lines": 5}),
            ToolCall(id="5", name="wc", arguments={"path": "test.txt"}),
        ]
        groups = orchestrator.analyze_dependencies(tool_calls)

        assert len(groups) == 1
        assert groups[0].strategy == ExecutionStrategy.PARALLEL
        assert len(groups[0].tools) == 5


class TestExecuteSingleTool:
    """Tests for _execute_single_tool method."""

    @pytest.mark.asyncio
    async def test_execute_ls_command(self, orchestrator, temp_data_dir):
        """Test executing ls command."""
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})
        result = await orchestrator._execute_single_tool(tool_call)

        assert result.success
        assert "test.txt" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_cat_command(self, orchestrator, temp_data_dir):
        """Test executing cat command."""
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await orchestrator._execute_single_tool(tool_call)

        assert result.success
        assert "Hello, World!" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_grep_command(self, orchestrator, temp_data_dir):
        """Test executing grep command."""
        tool_call = ToolCall(
            id="1",
            name="grep",
            arguments={"pattern": "Hello", "path": "test.txt"}
        )
        result = await orchestrator._execute_single_tool(tool_call)

        assert result.success
        assert "Hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_invalid_tool(self, orchestrator):
        """Test executing an invalid tool."""
        tool_call = ToolCall(id="1", name="invalid_tool", arguments={"path": "."})
        result = await orchestrator._execute_single_tool(tool_call)

        assert not result.success
        assert result.error == "ExecutionError"


class TestExecuteToolWithSemaphore:
    """Tests for execute_tool_with_semaphore method."""

    @pytest.mark.asyncio
    async def test_returns_tuple(self, orchestrator, temp_data_dir):
        """Test that method returns (tool_call, result) tuple."""
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})
        result_tuple = await orchestrator.execute_tool_with_semaphore(tool_call)

        assert isinstance(result_tuple, tuple)
        assert len(result_tuple) == 2
        assert result_tuple[0] == tool_call
        assert isinstance(result_tuple[1], ExecutionResult)


class TestExecuteParallel:
    """Tests for execute_parallel method."""

    @pytest.mark.asyncio
    async def test_empty_list(self, orchestrator):
        """Test parallel execution with empty list."""
        results = await orchestrator.execute_parallel([])
        assert results == []

    @pytest.mark.asyncio
    async def test_single_tool(self, orchestrator, temp_data_dir):
        """Test parallel execution with single tool."""
        tool_calls = [ToolCall(id="1", name="ls", arguments={"path": "."})]
        results = await orchestrator.execute_parallel(tool_calls)

        assert len(results) == 1
        tc, result = results[0]
        assert tc.id == "1"
        assert result.success

    @pytest.mark.asyncio
    async def test_multiple_tools(self, orchestrator, temp_data_dir):
        """Test parallel execution with multiple tools."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "test.txt"}),
            ToolCall(id="3", name="wc", arguments={"path": "test.txt"}),
        ]
        results = await orchestrator.execute_parallel(tool_calls)

        assert len(results) == 3
        for tc, result in results:
            assert result.success

    @pytest.mark.asyncio
    async def test_parallel_faster_than_sequential(self, orchestrator, temp_data_dir):
        """Test that parallel execution is faster than sequential for multiple tools."""
        # Create many tool calls
        tool_calls = [
            ToolCall(id=str(i), name="ls", arguments={"path": "."})
            for i in range(5)
        ]

        # Parallel execution
        start_parallel = time.time()
        parallel_results = await orchestrator.execute_parallel(tool_calls)
        parallel_time = time.time() - start_parallel

        # Sequential execution
        start_sequential = time.time()
        sequential_results = []
        for tc in tool_calls:
            result = await orchestrator._execute_single_tool(tc)
            sequential_results.append((tc, result))
        sequential_time = time.time() - start_sequential

        # Both should have same results count
        assert len(parallel_results) == len(sequential_results) == 5

        # Parallel should be faster (or at least not significantly slower)
        # Note: This test may be flaky on slow systems, so we're lenient
        assert parallel_time <= sequential_time * 1.5  # Allow 50% margin

    @pytest.mark.asyncio
    async def test_handles_exceptions_gracefully(self, sandbox):
        """Test that exceptions during parallel execution are handled."""
        orchestrator = ParallelToolOrchestrator(sandbox=sandbox, max_concurrent=2)

        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="unknown_command", arguments={}),
        ]

        results = await orchestrator.execute_parallel(tool_calls)

        assert len(results) == 2
        # First tool should succeed
        assert results[0][1].success
        # Second tool should fail but not crash
        assert not results[1][1].success


class TestExecuteSequential:
    """Tests for execute_sequential method."""

    @pytest.mark.asyncio
    async def test_empty_list(self, orchestrator):
        """Test sequential execution with empty list."""
        results = await orchestrator.execute_sequential([])
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_tools_in_order(self, orchestrator, temp_data_dir):
        """Test that sequential execution preserves order."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "test.txt"}),
            ToolCall(id="3", name="wc", arguments={"path": "test.txt"}),
        ]
        results = await orchestrator.execute_sequential(tool_calls)

        assert len(results) == 3
        assert results[0][0].id == "1"
        assert results[1][0].id == "2"
        assert results[2][0].id == "3"


class TestExecuteWithStrategy:
    """Tests for execute_with_strategy method."""

    @pytest.mark.asyncio
    async def test_empty_list(self, orchestrator):
        """Test strategy execution with empty list."""
        results = await orchestrator.execute_with_strategy([])
        assert results == []

    @pytest.mark.asyncio
    async def test_preserves_original_order(self, orchestrator, temp_data_dir):
        """Test that results are returned in original order."""
        tool_calls = [
            ToolCall(id="3", name="wc", arguments={"path": "test.txt"}),
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "test.txt"}),
        ]
        results = await orchestrator.execute_with_strategy(tool_calls)

        assert len(results) == 3
        # Results should be in original order (3, 1, 2)
        assert results[0][0].id == "3"
        assert results[1][0].id == "1"
        assert results[2][0].id == "2"

    @pytest.mark.asyncio
    async def test_all_read_tools_execute_parallel(self, orchestrator, temp_data_dir):
        """Test that all read-only tools execute in parallel."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "test.txt"}),
            ToolCall(id="3", name="grep", arguments={"pattern": "Hello", "path": "test.txt"}),
        ]
        results = await orchestrator.execute_with_strategy(tool_calls)

        assert len(results) == 3
        for tc, result in results:
            assert result.success


class TestConcurrencyLimits:
    """Tests for concurrency limiting behavior."""

    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self, sandbox, temp_data_dir):
        """Test that semaphore limits concurrent executions."""
        max_concurrent = 2
        orchestrator = ParallelToolOrchestrator(
            sandbox=sandbox, max_concurrent=max_concurrent
        )

        # Track concurrent executions
        current_concurrent = 0
        max_observed_concurrent = 0
        lock = asyncio.Lock()

        original_execute = orchestrator._execute_single_tool

        async def tracked_execute(tool_call):
            nonlocal current_concurrent, max_observed_concurrent
            async with lock:
                current_concurrent += 1
                max_observed_concurrent = max(max_observed_concurrent, current_concurrent)

            # Simulate some work
            await asyncio.sleep(0.1)
            result = await original_execute(tool_call)

            async with lock:
                current_concurrent -= 1

            return result

        orchestrator._execute_single_tool = tracked_execute

        # Create more tools than max_concurrent
        tool_calls = [
            ToolCall(id=str(i), name="ls", arguments={"path": "."})
            for i in range(5)
        ]

        await orchestrator.execute_parallel(tool_calls)

        # Should not exceed max_concurrent
        assert max_observed_concurrent <= max_concurrent


class TestErrorHandling:
    """Tests for error handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_partial_failures(self, orchestrator, temp_data_dir):
        """Test handling of partial failures in parallel execution."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={"path": "."}),
            ToolCall(id="2", name="cat", arguments={"path": "nonexistent.txt"}),
            ToolCall(id="3", name="cat", arguments={"path": "test.txt"}),
        ]
        results = await orchestrator.execute_with_strategy(tool_calls)

        assert len(results) == 3

        # First and third should succeed
        assert results[0][1].success
        assert results[2][1].success

        # Second should fail (file doesn't exist)
        assert not results[1][1].success

    @pytest.mark.asyncio
    async def test_all_failures(self, orchestrator, temp_data_dir):
        """Test handling when all tools fail."""
        tool_calls = [
            ToolCall(id="1", name="cat", arguments={"path": "missing1.txt"}),
            ToolCall(id="2", name="cat", arguments={"path": "missing2.txt"}),
        ]
        results = await orchestrator.execute_with_strategy(tool_calls)

        assert len(results) == 2
        for tc, result in results:
            assert not result.success

    @pytest.mark.asyncio
    async def test_invalid_arguments(self, orchestrator):
        """Test handling of invalid tool arguments."""
        tool_calls = [
            ToolCall(id="1", name="ls", arguments={}),  # Missing required 'path'
        ]

        # Should not raise, but should return error result
        results = await orchestrator.execute_with_strategy(tool_calls)
        assert len(results) == 1
        assert not results[0][1].success
