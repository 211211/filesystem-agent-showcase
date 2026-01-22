"""
Filesystem Agent - Core agent logic using OpenAI function calling with filesystem tools.
Inspired by Vercel's approach: https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash
"""

import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from openai import AsyncAzureOpenAI

from app.agent.tools.bash_tools import BASH_TOOLS, build_command
from app.agent.prompts import SYSTEM_PROMPT
from app.sandbox.executor import SandboxExecutor, ExecutionResult

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
    ):
        """
        Initialize the filesystem agent.

        Args:
            client: Azure OpenAI async client
            deployment_name: The deployment/model name to use
            data_root: Root directory for file operations
            sandbox: The sandbox executor for running commands
            max_tool_iterations: Maximum number of tool call iterations
        """
        self.client = client
        self.deployment_name = deployment_name
        self.data_root = data_root
        self.sandbox = sandbox
        self.max_tool_iterations = max_tool_iterations

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

            # Execute each tool and add results
            for tc in tool_calls:
                result = await self._execute_tool(tc)
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

    Returns:
        Configured FilesystemAgent instance
    """
    client = AsyncAzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )

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
    )
