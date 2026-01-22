"""
Chat API routes for the Filesystem Agent.
"""

import json
import uuid
import logging
from typing import Optional, AsyncGenerator
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings, Settings
from app.agent.filesystem_agent import create_agent, FilesystemAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# In-memory session storage (use Redis/DB in production)
_sessions: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=4096, description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class ToolCallResponse(BaseModel):
    """Response model for a tool call."""
    id: str
    name: str
    arguments: dict


class ToolResultResponse(BaseModel):
    """Response model for a tool result."""
    tool_call_id: str
    tool_name: str
    result: dict


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="Agent's response message")
    session_id: str = Field(..., description="Session ID for follow-up messages")
    tool_calls: list[ToolCallResponse] = Field(
        default_factory=list,
        description="List of tools called by the agent"
    )
    tool_results: list[ToolResultResponse] = Field(
        default_factory=list,
        description="Results from tool executions"
    )


def get_agent(settings: Settings = Depends(get_settings)) -> FilesystemAgent:
    """Dependency to get the filesystem agent."""
    return create_agent(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment_name,
        api_version=settings.azure_openai_api_version,
        data_root=settings.data_root,
        sandbox_enabled=settings.sandbox_enabled,
        command_timeout=settings.command_timeout,
        max_file_size=settings.max_file_size,
        max_output_size=settings.max_output_size,
        parallel_execution=settings.parallel_execution,
        max_concurrent_tools=settings.max_concurrent_tools,
        cache_enabled=settings.cache_enabled,
        cache_ttl=settings.cache_ttl,
        cache_max_size=settings.cache_max_size,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: FilesystemAgent = Depends(get_agent),
):
    """
    Send a message to the filesystem agent.

    The agent can search, read, and analyze files in the data directory
    using bash tools like grep, find, cat, ls, and tree.

    Example queries:
    - "What files are in the knowledge-base folder?"
    - "Find all markdown files in projects"
    - "Search for TODO comments in the codebase"
    - "Summarize the README file in project-alpha"
    """
    try:
        # Get or create session
        session_id = request.session_id or str(uuid.uuid4())
        history = _sessions.get(session_id, [])

        logger.info(f"Processing chat request for session {session_id}")

        # Get agent response
        response = await agent.chat(
            user_message=request.message,
            history=history,
        )

        # Update session history
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": response.message})
        _sessions[session_id] = history

        # Limit session history to prevent memory issues
        if len(_sessions[session_id]) > 50:
            _sessions[session_id] = _sessions[session_id][-50:]

        return ChatResponse(
            response=response.message,
            session_id=session_id,
            tool_calls=[
                ToolCallResponse(
                    id=tc.id,
                    name=tc.name,
                    arguments=tc.arguments,
                )
                for tc in response.tool_calls
            ],
            tool_results=[
                ToolResultResponse(
                    tool_call_id=tr["tool_call_id"],
                    tool_name=tr["tool_name"],
                    result=tr["result"],
                )
                for tr in response.tool_results
            ],
        )

    except Exception as e:
        logger.exception(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """Clear a chat session's history."""
    if session_id in _sessions:
        del _sessions[session_id]
        return {"message": f"Session {session_id} cleared"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Get the chat history for a session."""
    if session_id in _sessions:
        return {"session_id": session_id, "history": _sessions[session_id]}
    raise HTTPException(status_code=404, detail="Session not found")


async def sse_event_generator(
    agent: FilesystemAgent,
    message: str,
    session_id: str,
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events from the agent's streaming response.

    Args:
        agent: The filesystem agent
        message: User message
        session_id: Session ID
        history: Conversation history

    Yields:
        SSE formatted strings
    """
    try:
        async for event_type, event_data in agent.chat_stream(message, history):
            # Add session_id to all events
            event_data["session_id"] = session_id
            yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

            # Update session history on done event
            if event_type == "done":
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": event_data.get("message", "")})
                _sessions[session_id] = history[-50:]  # Limit history

    except Exception as e:
        logger.exception(f"Error in SSE generator: {e}")
        error_data = {
            "message": str(e),
            "type": type(e).__name__,
            "session_id": session_id,
        }
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    agent: FilesystemAgent = Depends(get_agent),
):
    """
    Stream a chat response via Server-Sent Events (SSE).

    This endpoint provides real-time streaming of:
    - Status updates (thinking, executing tools)
    - Tool calls as they are made
    - Tool results as they complete
    - LLM response tokens as they are generated
    - Final done event with complete message

    **SSE Event Types:**

    - `status`: Progress updates
      ```
      event: status
      data: {"stage": "thinking", "message": "Analyzing...", "session_id": "..."}
      ```

    - `tool_call`: When agent decides to call a tool
      ```
      event: tool_call
      data: {"id": "call_1", "name": "grep", "arguments": {...}, "session_id": "..."}
      ```

    - `tool_result`: When tool execution completes
      ```
      event: tool_result
      data: {"id": "call_1", "name": "grep", "success": true, "output": "...", "session_id": "..."}
      ```

    - `token`: LLM response tokens (streamed one by one)
      ```
      event: token
      data: {"content": "I", "session_id": "..."}
      ```

    - `done`: Final event with complete response
      ```
      event: done
      data: {"message": "Full response...", "tool_calls_count": 2, "iterations": 1, "session_id": "..."}
      ```

    - `error`: If an error occurs
      ```
      event: error
      data: {"message": "Error details", "type": "ErrorType", "session_id": "..."}
      ```

    **Example usage with curl:**
    ```bash
    curl -N -X POST http://localhost:8000/api/chat/stream \\
      -H "Content-Type: application/json" \\
      -d '{"message": "Find all markdown files"}'
    ```

    **Example usage with JavaScript:**
    ```javascript
    const eventSource = new EventSource('/api/chat/stream', {
      method: 'POST',
      body: JSON.stringify({message: 'Find all markdown files'})
    });

    eventSource.addEventListener('token', (e) => {
      const data = JSON.parse(e.data);
      console.log(data.content); // Stream tokens
    });

    eventSource.addEventListener('done', (e) => {
      const data = JSON.parse(e.data);
      console.log(data.message); // Final message
    });
    ```
    """
    try:
        # Get or create session
        session_id = request.session_id or str(uuid.uuid4())
        history = _sessions.get(session_id, [])

        logger.info(f"Starting streaming chat for session {session_id}")

        return StreamingResponse(
            sse_event_generator(agent, request.message, session_id, history),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.exception(f"Error starting streaming chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
