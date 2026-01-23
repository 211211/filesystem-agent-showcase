"""
Orchestrator interface for tool execution coordination.

This module defines the IToolOrchestrator interface that abstracts
the coordination and execution of multiple tool calls, enabling
different execution strategies (parallel, sequential, batched).
"""

from abc import ABC, abstractmethod
from typing import Any, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.sandbox.executor import ExecutionResult
    from app.agent.filesystem_agent import ToolCall
    from app.agent.orchestrator import ToolGroup


class IToolOrchestrator(ABC):
    """
    Abstract interface for tool execution orchestration.

    Implementations coordinate the execution of multiple tool calls,
    potentially in parallel, sequential, or batched strategies based
    on dependency analysis.

    Implementations:
        - ParallelToolOrchestrator: Production implementation with
          semaphore-based concurrency control

    Example:
        ```python
        class SimpleOrchestrator(IToolOrchestrator):
            def __init__(self, executor: IExecutor):
                self._executor = executor
                self._max_concurrent = 5

            @property
            def max_concurrent(self) -> int:
                return self._max_concurrent

            async def execute_parallel(self, tool_calls):
                # Execute all tools concurrently
                tasks = [self._execute(tc) for tc in tool_calls]
                results = await asyncio.gather(*tasks)
                return list(zip(tool_calls, results))

            async def execute_sequential(self, tool_calls):
                results = []
                for tc in tool_calls:
                    result = await self._execute(tc)
                    results.append((tc, result))
                return results

            async def execute_with_strategy(self, tool_calls):
                groups = self.analyze_dependencies(tool_calls)
                all_results = []
                for group in groups:
                    if group.strategy == ExecutionStrategy.PARALLEL:
                        results = await self.execute_parallel(group.tools)
                    else:
                        results = await self.execute_sequential(group.tools)
                    all_results.extend(results)
                return all_results

            def analyze_dependencies(self, tool_calls):
                # Simple implementation: all read-only tools in parallel
                ...
        ```
    """

    @property
    @abstractmethod
    def max_concurrent(self) -> int:
        """
        Get the maximum number of concurrent executions.

        Returns:
            Maximum concurrency limit for parallel execution
        """
        pass

    @abstractmethod
    async def execute_parallel(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", "ExecutionResult"]]:
        """
        Execute multiple tool calls in parallel.

        Uses asyncio.gather with semaphore for concurrency control.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples in the same order as input
        """
        pass

    @abstractmethod
    async def execute_sequential(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", "ExecutionResult"]]:
        """
        Execute tool calls sequentially (one at a time).

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples in the same order as input
        """
        pass

    @abstractmethod
    async def execute_with_strategy(
        self,
        tool_calls: List["ToolCall"],
    ) -> List[Tuple["ToolCall", "ExecutionResult"]]:
        """
        Execute tool calls using optimal strategy based on analysis.

        This is the main entry point for executing tool calls. It:
        1. Analyzes dependencies between tool calls
        2. Groups tools by execution strategy
        3. Executes groups in dependency order
        4. Returns results in original tool_calls order

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples preserving original order
        """
        pass

    @abstractmethod
    def analyze_dependencies(
        self,
        tool_calls: List["ToolCall"],
    ) -> List["ToolGroup"]:
        """
        Analyze tool calls to determine execution strategy.

        Separates tool calls into groups based on their characteristics:
        - Read-only tools (grep, find, cat, ls, etc.): Can run in parallel
        - Write tools: Must run sequentially
        - Unknown tools: Default to sequential for safety

        Args:
            tool_calls: List of tool calls to analyze

        Returns:
            List of ToolGroup objects with appropriate execution strategies
        """
        pass
