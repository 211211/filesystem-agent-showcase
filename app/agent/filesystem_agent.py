"""
Filesystem Agent - Core agent logic using OpenAI function calling with filesystem tools.
Inspired by Vercel's approach: https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash
"""

import json
import logging
from pathlib import Path
from typing import Optional, AsyncGenerator, Any, Callable, Awaitable
from dataclasses import dataclass, field
from openai import AsyncAzureOpenAI

from app.agent.tools.bash_tools import BASH_TOOLS, build_command
from app.agent.prompts import SYSTEM_PROMPT
from app.sandbox.executor import SandboxExecutor, ExecutionResult
from app.sandbox.cached_executor import CachedSandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator
from app.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to OpenAI message format."""
        msg = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: dict

    def to_dict(self) -> dict:
        """Convert to serializable format."""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class AgentResponse:
    """Response from the filesystem agent."""
    message: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to serializable format."""
        return {
            "message": self.message,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tool_results": self.tool_results,
        }


class FilesystemAgent:
    """
    An AI agent that can explore and analyze files using bash tools.

    This agent uses OpenAI's function calling to let the LLM decide which
    filesystem operations to perform, then executes them in a sandboxed
    environment.
    """

    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment_name: str,
        data_root: Path,
        sandbox: SandboxExecutor,
        max_tool_iterations: int = 10,
        parallel_execution: bool = True,
        max_concurrent_tools: int = 5,
        cache_manager: Optional[CacheManager] = None,
    ):
        """
        Initialize the filesystem agent.

        Args:
            client: Azure OpenAI async client
            deployment_name: The deployment/model name to use
            data_root: Root directory for file operations
            sandbox: The sandbox executor for running commands
            max_tool_iterations: Maximum number of tool call iterations
            parallel_execution: Whether to enable parallel tool execution
            max_concurrent_tools: Maximum number of concurrent tool executions
            cache_manager: Optional CacheManager for advanced caching (new system)
        """
        self.client = client
        self.deployment_name = deployment_name
        self.data_root = data_root
        self.sandbox = sandbox
        self.max_tool_iterations = max_tool_iterations
        self.parallel_execution = parallel_execution
        self.max_concurrent_tools = max_concurrent_tools
        self.cache_manager = cache_manager

        # Initialize orchestrator for parallel execution
        if parallel_execution:
            self._orchestrator = ParallelToolOrchestrator(
                sandbox=sandbox,
                max_concurrent=max_concurrent_tools,
            )
        else:
            self._orchestrator = None

    async def _execute_tool(self, tool_call: ToolCall) -> ExecutionResult:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute

        Returns:
            The execution result
        """
        logger.info(f"Executing tool: {tool_call.name} with args: {tool_call.arguments}")

        try:
            # If new cache manager is available, use cached versions for read/search operations
            if self.cache_manager is not None:
                if tool_call.name in ("cat", "head"):
                    return await self._cached_read_file(tool_call)
                elif tool_call.name in ("grep", "find"):
                    return await self._cached_search(tool_call)
                # Other operations (ls, wc, tree, etc.) fall through to regular execution

            # Build the command from tool name and arguments
            command = build_command(tool_call.name, tool_call.arguments)
            logger.debug(f"Built command: {command}")

            # Execute in sandbox
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

    async def _cached_read_file(self, tool_call: ToolCall) -> ExecutionResult:
        """
        Execute a file read operation with caching.

        This method uses the CacheManager's ContentCache to cache file contents,
        avoiding repeated disk reads. The cache automatically detects when files
        have changed and invalidates stale entries.

        Args:
            tool_call: The tool call to execute (cat or head)

        Returns:
            The execution result with cached or fresh content
        """
        path_str = tool_call.arguments.get("path", "")
        file_path = (self.data_root / path_str).resolve()

        try:
            # Define the loader function that reads from disk
            async def load_file(p: Path) -> str:
                # Build and execute the command normally
                command = build_command(tool_call.name, tool_call.arguments)
                result = await self.sandbox.execute(command)
                if result.success:
                    return result.stdout
                else:
                    raise Exception(f"Failed to read file: {result.stderr}")

            # Get content from cache or load fresh
            content = await self.cache_manager.content_cache.get_content(
                file_path,
                load_file
            )

            # Build command string for logging
            command = build_command(tool_call.name, tool_call.arguments)

            return ExecutionResult(
                success=True,
                stdout=content,
                stderr="",
                return_code=0,
                command=" ".join(command),
                error=None,
            )

        except Exception as e:
            logger.error(f"Error in cached read for {tool_call.name}: {e}")
            command = build_command(tool_call.name, tool_call.arguments)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=" ".join(command),
                error="CachedReadError",
            )

    async def _cached_search(self, tool_call: ToolCall) -> ExecutionResult:
        """
        Execute a search operation with caching.

        This method uses the CacheManager's SearchCache to cache search results,
        avoiding repeated expensive searches. The cache automatically detects when
        files in the search scope have changed and invalidates stale results.

        Args:
            tool_call: The tool call to execute (grep or find)

        Returns:
            The execution result with cached or fresh search results
        """
        try:
            # Extract search parameters
            if tool_call.name == "grep":
                pattern = tool_call.arguments.get("pattern", "")
                path_str = tool_call.arguments.get("path", "")
                scope = (self.data_root / path_str).resolve()
                options = {
                    "recursive": tool_call.arguments.get("recursive", True),
                    "ignore_case": tool_call.arguments.get("ignore_case", False),
                }
            elif tool_call.name == "find":
                pattern = tool_call.arguments.get("name_pattern", "")
                path_str = tool_call.arguments.get("path", "")
                scope = (self.data_root / path_str).resolve()
                options = {
                    "type": tool_call.arguments.get("type", "f"),
                }
            else:
                # Unknown search operation, fallback to regular execution
                raise ValueError(f"Unknown search operation: {tool_call.name}")

            # Try to get from cache
            cached_result = await self.cache_manager.search_cache.get_search_result(
                operation=tool_call.name,
                pattern=pattern,
                scope=scope,
                options=options,
            )

            if cached_result is not None:
                # Cache hit
                command = build_command(tool_call.name, tool_call.arguments)
                return ExecutionResult(
                    success=True,
                    stdout=cached_result,
                    stderr="",
                    return_code=0,
                    command=" ".join(command),
                    error=None,
                )

            # Cache miss - execute and cache the result
            command = build_command(tool_call.name, tool_call.arguments)
            result = await self.sandbox.execute(command)

            if result.success:
                # Cache the successful result
                await self.cache_manager.search_cache.set_search_result(
                    operation=tool_call.name,
                    pattern=pattern,
                    scope=scope,
                    options=options,
                    result=result.stdout,
                    ttl=300,  # 5 minutes TTL
                )

            return result

        except Exception as e:
            logger.error(f"Error in cached search for {tool_call.name}: {e}")
            # Fallback to regular execution on error
            command = build_command(tool_call.name, tool_call.arguments)
            result = await self.sandbox.execute(command)
            return result

    def _parse_tool_calls(self, response_message) -> list[ToolCall]:
        """Parse tool calls from the LLM response."""
        tool_calls = []
        if response_message.tool_calls:
            for tc in response_message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": tc.function.arguments}

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                ))
        return tool_calls

    async def _execute_tools_parallel(
        self,
        tool_calls: list[ToolCall],
    ) -> list[tuple[ToolCall, ExecutionResult]]:
        """
        Execute multiple tool calls in parallel using the orchestrator.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples
        """
        if not self._orchestrator:
            # Fallback to sequential execution if orchestrator not available
            results = []
            for tc in tool_calls:
                result = await self._execute_tool(tc)
                results.append((tc, result))
            return results

        return await self._orchestrator.execute_with_strategy(tool_calls)

    async def _execute_tools_sequential(
        self,
        tool_calls: list[ToolCall],
    ) -> list[tuple[ToolCall, ExecutionResult]]:
        """
        Execute tool calls sequentially (original behavior).

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            List of (tool_call, result) tuples
        """
        results = []
        for tc in tool_calls:
            result = await self._execute_tool(tc)
            results.append((tc, result))
        return results

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics from all cache systems.

        Returns:
            Dictionary with cache statistics:
            - new_cache: Stats from CacheManager (if enabled)
            - old_cache: Stats from CachedSandboxExecutor (if enabled)

        Example:
            >>> agent = create_agent(...)
            >>> stats = agent.get_cache_stats()
            >>> print(f"Cache size: {stats['new_cache']['disk_cache']['size']} entries")
            >>> print(f"Disk usage: {stats['new_cache']['disk_cache']['volume']} bytes")
        """
        stats = {}

        # Get stats from new cache system
        if self.cache_manager is not None:
            stats["new_cache"] = self.cache_manager.stats()
        else:
            stats["new_cache"] = {"enabled": False}

        # Get stats from old cache system (CachedSandboxExecutor)
        if isinstance(self.sandbox, CachedSandboxExecutor):
            stats["old_cache"] = self.sandbox.cache_stats()
        else:
            stats["old_cache"] = {"enabled": False}

        return stats

    async def chat(
        self,
        user_message: str,
        history: Optional[list[dict]] = None,
    ) -> AgentResponse:
        """
        Process a user message and return a response.

        This method implements the agent loop:
        1. Send the message to the LLM with available tools
        2. If the LLM wants to use tools, execute them
        3. Send the results back to the LLM
        4. Repeat until the LLM returns a final response

        Args:
            user_message: The user's message
            history: Optional conversation history

        Returns:
            AgentResponse with the final message and tool execution details
        """
        # Build message history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_message})

        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[dict] = []

        # Agent loop
        for iteration in range(self.max_tool_iterations):
            logger.info(f"Agent iteration {iteration + 1}/{self.max_tool_iterations}")

            # Call the LLM
            response = await self.client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                tools=BASH_TOOLS,
                tool_choice="auto",
            )

            response_message = response.choices[0].message

            # Check if we need to execute tools
            if not response_message.tool_calls:
                # No tool calls, return the response
                return AgentResponse(
                    message=response_message.content or "",
                    tool_calls=all_tool_calls,
                    tool_results=all_tool_results,
                )

            # Parse and execute tool calls
            tool_calls = self._parse_tool_calls(response_message)
            all_tool_calls.extend(tool_calls)

            # Add assistant message with tool calls to history
            messages.append({
                "role": "assistant",
                "content": response_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in tool_calls
                ]
            })

            # Execute tools (parallel or sequential based on configuration)
            if self.parallel_execution and len(tool_calls) > 1:
                logger.info(f"Executing {len(tool_calls)} tools in parallel")
                execution_results = await self._execute_tools_parallel(tool_calls)
            else:
                logger.info(f"Executing {len(tool_calls)} tools sequentially")
                execution_results = await self._execute_tools_sequential(tool_calls)

            # Process results and add to messages
            for tc, result in execution_results:
                tool_result = {
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                    "result": result.to_dict(),
                }
                all_tool_results.append(tool_result)

                # Add tool result to messages
                output = result.stdout if result.success else f"Error: {result.stderr}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                })

        # Max iterations reached
        logger.warning("Max tool iterations reached")
        return AgentResponse(
            message="I've reached the maximum number of operations. Here's what I found so far based on the tool results above.",
            tool_calls=all_tool_calls,
            tool_results=all_tool_results,
        )

    async def chat_stream(
        self,
        user_message: str,
        history: Optional[list[dict]] = None,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        """
        Process a user message and stream the response as SSE events.

        This method implements the same agent loop as chat() but yields
        events as they occur for real-time streaming.

        Event types:
        - status: {"stage": str, "message": str}
        - tool_call: {"id": str, "name": str, "arguments": dict}
        - tool_result: {"id": str, "name": str, "success": bool, "output": str}
        - token: {"content": str}
        - done: {"message": str, "tool_calls_count": int, "iterations": int}
        - error: {"message": str, "type": str}

        Args:
            user_message: The user's message
            history: Optional conversation history

        Yields:
            Tuples of (event_type, event_data)
        """
        # Build message history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_message})

        all_tool_calls: list[ToolCall] = []
        total_iterations = 0

        yield ("status", {"stage": "thinking", "message": "Analyzing your request..."})

        # Agent loop
        for iteration in range(self.max_tool_iterations):
            total_iterations = iteration + 1
            logger.info(f"Agent iteration {iteration + 1}/{self.max_tool_iterations}")

            yield ("status", {
                "stage": "llm_call",
                "message": f"Calling LLM (iteration {iteration + 1})...",
                "iteration": iteration + 1,
            })

            try:
                # Call the LLM with streaming
                stream = await self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    tools=BASH_TOOLS,
                    tool_choice="auto",
                    stream=True,
                )

                # Collect the streamed response
                collected_content = ""
                collected_tool_calls: list[dict] = []
                current_tool_call: dict = {}

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None

                    if delta is None:
                        continue

                    # Stream content tokens
                    if delta.content:
                        collected_content += delta.content
                        yield ("token", {"content": delta.content})

                    # Collect tool calls
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index

                            # Extend list if needed
                            while len(collected_tool_calls) <= idx:
                                collected_tool_calls.append({
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                })

                            if tc_delta.id:
                                collected_tool_calls[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    collected_tool_calls[idx]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments

                # Check if we have tool calls to execute
                if not collected_tool_calls:
                    # No tool calls, we're done
                    yield ("done", {
                        "message": collected_content,
                        "tool_calls_count": len(all_tool_calls),
                        "iterations": total_iterations,
                    })
                    return

                # Parse tool calls
                tool_calls = []
                for tc_data in collected_tool_calls:
                    try:
                        arguments = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                    except json.JSONDecodeError:
                        arguments = {"raw": tc_data["arguments"]}

                    tc = ToolCall(
                        id=tc_data["id"],
                        name=tc_data["name"],
                        arguments=arguments,
                    )
                    tool_calls.append(tc)
                    all_tool_calls.append(tc)

                    # Emit tool_call event
                    yield ("tool_call", {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    })

                # Add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": collected_content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            }
                        }
                        for tc in tool_calls
                    ]
                })

                # Execute tools
                yield ("status", {
                    "stage": "executing_tools",
                    "message": f"Executing {len(tool_calls)} tool(s)...",
                    "tool_count": len(tool_calls),
                })

                if self.parallel_execution and len(tool_calls) > 1:
                    logger.info(f"Executing {len(tool_calls)} tools in parallel")
                    execution_results = await self._execute_tools_parallel(tool_calls)
                else:
                    logger.info(f"Executing {len(tool_calls)} tools sequentially")
                    execution_results = await self._execute_tools_sequential(tool_calls)

                # Process and stream results
                for tc, result in execution_results:
                    output = result.stdout if result.success else f"Error: {result.stderr}"

                    yield ("tool_result", {
                        "id": tc.id,
                        "name": tc.name,
                        "success": result.success,
                        "output": output[:1000] + "..." if len(output) > 1000 else output,  # Truncate for streaming
                    })

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": output,
                    })

            except Exception as e:
                logger.exception(f"Error in chat_stream: {e}")
                yield ("error", {
                    "message": str(e),
                    "type": type(e).__name__,
                })
                return

        # Max iterations reached
        logger.warning("Max tool iterations reached")
        yield ("status", {
            "stage": "max_iterations",
            "message": "Maximum iterations reached",
        })
        yield ("done", {
            "message": "I've reached the maximum number of operations. Here's what I found so far.",
            "tool_calls_count": len(all_tool_calls),
            "iterations": total_iterations,
        })


def create_agent(
    api_key: str,
    endpoint: str,
    deployment_name: str,
    api_version: str,
    data_root: Path,
    sandbox_enabled: bool = True,
    command_timeout: int = 30,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB default
    max_output_size: int = 1024 * 1024,  # 1MB default
    parallel_execution: bool = True,
    max_concurrent_tools: int = 5,
    cache_enabled: bool = True,
    cache_ttl: int = 300,
    cache_max_size: int = 100,
    # New cache system parameters
    use_new_cache: bool = False,
    cache_directory: str = "tmp/cache",
    cache_size_limit: int = 500 * 1024 * 1024,
    cache_content_ttl: float = 0,
    cache_search_ttl: float = 300,
) -> FilesystemAgent:
    """
    Factory function to create a FilesystemAgent.

    Args:
        api_key: Azure OpenAI API key
        endpoint: Azure OpenAI endpoint
        deployment_name: Model deployment name
        api_version: API version
        data_root: Root directory for file operations
        sandbox_enabled: Whether to enable sandbox security
        command_timeout: Command execution timeout in seconds
        max_file_size: Maximum file size for cat operations in bytes (default: 10MB)
        max_output_size: Maximum output size in bytes (default: 1MB)
        parallel_execution: Whether to enable parallel tool execution
        max_concurrent_tools: Maximum number of concurrent tool executions
        cache_enabled: Whether to enable old cache system (CachedSandboxExecutor)
        cache_ttl: Old cache TTL in seconds (default: 300 = 5 minutes)
        cache_max_size: Maximum number of cached entries for old cache (default: 100)
        use_new_cache: Whether to use new CacheManager system (default: False for backward compatibility)
        cache_directory: Directory for new cache storage (default: "tmp/cache")
        cache_size_limit: Maximum size for new cache in bytes (default: 500MB)
        cache_content_ttl: TTL for content cache (default: 0 = no expiry)
        cache_search_ttl: TTL for search cache (default: 300 = 5 minutes)

    Returns:
        Configured FilesystemAgent instance
    """
    client = AsyncAzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )

    # Initialize new cache system if enabled
    cache_manager = None
    if use_new_cache:
        logger.info("Initializing new CacheManager system")
        cache_manager = CacheManager(
            cache_dir=cache_directory,
            size_limit=cache_size_limit,
            content_ttl=cache_content_ttl,
            search_ttl=cache_search_ttl,
        )

    # Use CachedSandboxExecutor when old caching is enabled, otherwise use regular SandboxExecutor
    if cache_enabled and not use_new_cache:
        logger.info("Using old CachedSandboxExecutor system")
        sandbox = CachedSandboxExecutor(
            root_path=data_root,
            timeout=command_timeout,
            max_file_size=max_file_size,
            max_output_size=max_output_size,
            enabled=sandbox_enabled,
            cache_enabled=cache_enabled,
            cache_ttl=cache_ttl,
            cache_max_size=cache_max_size,
        )
    else:
        logger.info("Using regular SandboxExecutor (no old cache)")
        sandbox = SandboxExecutor(
            root_path=data_root,
            timeout=command_timeout,
            max_file_size=max_file_size,
            max_output_size=max_output_size,
            enabled=sandbox_enabled,
        )

    return FilesystemAgent(
        client=client,
        deployment_name=deployment_name,
        data_root=data_root,
        sandbox=sandbox,
        parallel_execution=parallel_execution,
        max_concurrent_tools=max_concurrent_tools,
        cache_manager=cache_manager,
    )
