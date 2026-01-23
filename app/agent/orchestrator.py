"""
Parallel Tool Orchestrator for the Filesystem Agent.
Enables concurrent execution of independent tool calls to improve performance.
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING, cast

from app.agent.tools.bash_tools import build_command
from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.interfaces.orchestrator import IToolOrchestrator

if TYPE_CHECKING:
    from app.agent.filesystem_agent import ToolCall

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Strategy for executing tool calls."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    BATCHED = "batched"


@dataclass
class ToolGroup:
    """A group of tools to execute with a specific strategy."""
    tools: list["ToolCall"]
    strategy: ExecutionStrategy
    depends_on: Optional[list[str]] = field(default_factory=list)


# Tools that only read data and don't modify state (safe for parallel execution)
READ_ONLY_TOOLS = frozenset({
    "grep",
    "find",
    "cat",
    "head",
    "ls",
    "tree",
    "wc",
    "tail",
})

# Tools that may modify state (should be sequential or carefully managed)
WRITE_TOOLS = frozenset({
    # Currently we don't have write tools, but this is for future extensibility
})


class ParallelToolOrchestrator(IToolOrchestrator):
    """
    Orchestrates parallel execution of tool calls.

    Implements the IToolOrchestrator interface.

    This orchestrator analyzes tool calls to determine which can be executed
    in parallel (read-only tools) and which need sequential execution.
    It uses asyncio.Semaphore to limit concurrency.
    """

    def __init__(
        self,
        sandbox: SandboxExecutor,
        max_concurrent: int = 5,
    ):
        """
        Initialize the parallel tool orchestrator.

        Args:
            sandbox: The sandbox executor for running commands
            max_concurrent: Maximum number of concurrent tool executions
        """
        self.sandbox = sandbox
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @property
    def max_concurrent(self) -> int:
        """Get the maximum number of concurrent executions."""
        return self._max_concurrent

    async def execute_tool_with_semaphore(
        self,
        tool_call: "ToolCall",
    ) -> tuple["ToolCall", ExecutionResult]:
        """
        Execute a single tool call with semaphore for concurrency control.

        Args:
            tool_call: The tool call to execute

        Returns:
            Tuple of (tool_call, execution_result)
        """
        async with self._semaphore:
            logger.debug(f"Executing tool (with semaphore): {tool_call.name}")
            result = await self._execute_single_tool(tool_call)
            return (tool_call, result)

    async def _execute_single_tool(
        self,
        tool_call: "ToolCall",
    ) -> ExecutionResult:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute

        Returns:
            The execution result
        """
        try:
            command = build_command(tool_call.name, tool_call.arguments)
            logger.debug(f"Built command for {tool_call.name}: {command}")
            result = await self.sandbox.execute(command)
            logger.info(f"Tool {tool_call.name} returned with code {result.return_code}")
            return result

        except Exception as e:
            logger.error(f"Error executing tool {tool_call.name}: {e}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=f"{tool_call.name} {tool_call.arguments}",
                error="ExecutionError",
            )

    async def execute_parallel(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", ExecutionResult]]:
        """
        Execute multiple tool calls in parallel using asyncio.gather.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples in the same order as input
        """
        if not tool_calls:
            return []

        logger.info(f"Executing {len(tool_calls)} tools in parallel (max concurrent: {self._max_concurrent})")

        # Create tasks for parallel execution
        tasks = [
            self.execute_tool_with_semaphore(tc)
            for tc in tool_calls
        ]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, handling any exceptions
        processed_results: List[Tuple["ToolCall", ExecutionResult]] = []
        for i, result in enumerate(results):
            tool_call = tool_calls[i]
            if isinstance(result, Exception):
                logger.error(f"Exception during parallel execution of {tool_call.name}: {result}")
                error_result = ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=str(result),
                    return_code=-1,
                    command=f"{tool_call.name} {tool_call.arguments}",
                    error="ParallelExecutionError",
                )
                processed_results.append((tool_call, error_result))
            else:
                # Type narrowing: result is Tuple[ToolCall, ExecutionResult] after Exception check
                processed_results.append(cast(Tuple["ToolCall", ExecutionResult], result))

        return processed_results

    async def execute_sequential(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", ExecutionResult]]:
        """
        Execute tool calls sequentially (one at a time).

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples in the same order as input
        """
        results: List[Tuple["ToolCall", ExecutionResult]] = []

        for tc in tool_calls:
            logger.info(f"Executing tool sequentially: {tc.name}")
            result = await self._execute_single_tool(tc)
            results.append((tc, result))

        return results

    def analyze_dependencies(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[ToolGroup]:
        """
        Analyze tool calls to determine execution strategy.

        All read-only tools (grep, find, cat, ls, etc.) are independent
        and can be executed in parallel. Write tools need sequential execution.

        Args:
            tool_calls: List of tool calls to analyze

        Returns:
            List of ToolGroup objects with appropriate execution strategies
        """
        if not tool_calls:
            return []

        # Separate read-only and write tools
        read_only_calls: List["ToolCall"] = []
        write_calls: List["ToolCall"] = []

        for tc in tool_calls:
            if tc.name in READ_ONLY_TOOLS:
                read_only_calls.append(tc)
            elif tc.name in WRITE_TOOLS:
                write_calls.append(tc)
            else:
                # Unknown tools default to sequential for safety
                logger.warning(f"Unknown tool {tc.name}, treating as sequential")
                write_calls.append(tc)

        groups: List[ToolGroup] = []

        # All read-only tools can be parallel
        if read_only_calls:
            groups.append(ToolGroup(
                tools=read_only_calls,
                strategy=ExecutionStrategy.PARALLEL,
                depends_on=[],
            ))

        # Write tools execute sequentially after read-only tools
        if write_calls:
            depends = ["read_only_group"] if read_only_calls else []
            groups.append(ToolGroup(
                tools=write_calls,
                strategy=ExecutionStrategy.SEQUENTIAL,
                depends_on=depends,
            ))

        return groups

    async def execute_with_strategy(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", ExecutionResult]]:
        """
        Execute tool calls using the appropriate strategy based on analysis.

        This is the main entry point for executing tool calls with optimal
        parallelization.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples preserving original order
        """
        if not tool_calls:
            return []

        # Analyze dependencies and create execution groups
        groups = self.analyze_dependencies(tool_calls)

        # Collect all results
        all_results: List[Tuple["ToolCall", ExecutionResult]] = []

        for group in groups:
            logger.info(f"Executing group with strategy: {group.strategy.value}, tools: {[t.name for t in group.tools]}")

            if group.strategy == ExecutionStrategy.PARALLEL:
                results = await self.execute_parallel(group.tools)
            else:
                results = await self.execute_sequential(group.tools)

            all_results.extend(results)

        # Reorder results to match original tool_calls order
        result_map = {tc.id: result for tc, result in all_results}
        ordered_results = [(tc, result_map[tc.id]) for tc in tool_calls if tc.id in result_map]

        return ordered_results
