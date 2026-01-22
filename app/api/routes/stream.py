"""
SSE streaming endpoints for file content and search results.
Provides real-time streaming of file data using Server-Sent Events (SSE).
"""

import json
import re
from pathlib import Path
from typing import AsyncGenerator, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.sandbox.executor import SandboxExecutor, PathTraversalError
from app.agent.tools.streaming import StreamingFileReader

router = APIRouter(prefix="/stream", tags=["stream"])


def get_sandbox() -> SandboxExecutor:
    """Get a SandboxExecutor instance with settings from config."""
    settings = get_settings()
    return SandboxExecutor(
        root_path=settings.data_root,
        timeout=settings.command_timeout,
        max_output_size=settings.max_output_size,
        max_file_size=settings.max_file_size,
        enabled=settings.sandbox_enabled,
    )


async def sse_generator(events: AsyncGenerator[Tuple[str, dict], None]) -> AsyncGenerator[str, None]:
    """
    Convert async event generator to SSE format.

    Args:
        events: Async generator yielding (event_type, data) tuples

    Yields:
        SSE formatted strings
    """
    async for event_type, data in events:
        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def stream_file_events(
    file_path: Path,
    chunk_size: int,
    total_size: int
) -> AsyncGenerator[Tuple[str, dict], None]:
    """
    Generate SSE events for streaming file content.

    Args:
        file_path: Path to the file to stream
        chunk_size: Size of each chunk in bytes
        total_size: Total file size for progress calculation

    Yields:
        Tuples of (event_type, data) for SSE
    """
    reader = StreamingFileReader(chunk_size=chunk_size)
    bytes_read = 0

    try:
        async for chunk in reader.read_chunks(file_path):
            chunk_bytes = len(chunk.encode('utf-8'))
            bytes_read += chunk_bytes
            percent = min(100, int((bytes_read / total_size) * 100)) if total_size > 0 else 100

            # Send progress event
            yield ("progress", {"percent": percent, "bytes_read": bytes_read})

            # Send chunk event
            yield ("chunk", {"content": chunk})

        # Send done event
        yield ("done", {"total_bytes": bytes_read})

    except Exception as e:
        yield ("error", {"message": str(e), "type": type(e).__name__})


async def stream_grep_events(
    file_path: Path,
    query: str,
    chunk_size: int,
    total_size: int
) -> AsyncGenerator[Tuple[str, dict], None]:
    """
    Generate SSE events for streaming grep results.

    Args:
        file_path: Path to the file to search
        query: Search query/pattern
        chunk_size: Size of each chunk to process
        total_size: Total file size for progress calculation

    Yields:
        Tuples of (event_type, data) for SSE
    """
    try:
        regex = re.compile(query)
    except re.error as e:
        yield ("error", {"message": f"Invalid regex pattern: {e}", "type": "InvalidPattern"})
        return

    reader = StreamingFileReader(chunk_size=chunk_size)
    bytes_read = 0
    line_number = 0
    matches_found = 0
    buffer = ""

    try:
        async for chunk in reader.read_chunks(file_path):
            chunk_bytes = len(chunk.encode('utf-8'))
            bytes_read += chunk_bytes
            percent = min(100, int((bytes_read / total_size) * 100)) if total_size > 0 else 100

            # Send progress event
            yield ("progress", {"percent": percent, "bytes_read": bytes_read})

            # Process chunk for matches (handle line boundaries)
            buffer += chunk
            lines = buffer.split('\n')
            # Keep the last incomplete line in buffer
            buffer = lines[-1]

            for line in lines[:-1]:
                line_number += 1
                match = regex.search(line)
                if match:
                    matches_found += 1
                    yield ("match", {
                        "line_number": line_number,
                        "line_content": line,
                        "match_start": match.start(),
                        "match_end": match.end()
                    })

        # Process any remaining buffer
        if buffer:
            line_number += 1
            match = regex.search(buffer)
            if match:
                matches_found += 1
                yield ("match", {
                    "line_number": line_number,
                    "line_content": buffer,
                    "match_start": match.start(),
                    "match_end": match.end()
                })

        # Send done event
        yield ("done", {"total_bytes": bytes_read, "matches_found": matches_found})

    except Exception as e:
        yield ("error", {"message": str(e), "type": type(e).__name__})


async def stream_search_events(
    file_path: Path,
    pattern: str,
    max_matches: int
) -> AsyncGenerator[Tuple[str, dict], None]:
    """
    Generate SSE events for streaming search results.

    Args:
        file_path: Path to the file to search
        pattern: Regex pattern to search for
        max_matches: Maximum number of matches to return

    Yields:
        Tuples of (event_type, data) for SSE
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        yield ("error", {"message": f"Invalid regex pattern: {e}", "type": "InvalidPattern"})
        return

    reader = StreamingFileReader()

    try:
        # Get file stats for progress
        stats = await reader.get_file_stats(file_path)
        total_size = stats.get('size_bytes', 0)
        estimated_lines = stats.get('line_count', 0) or 1

        matches_found = 0
        bytes_read = 0

        async for line_number, line in reader.read_lines(file_path):
            # Estimate progress based on lines
            percent = min(100, int((line_number / estimated_lines) * 100))
            bytes_read += len(line.encode('utf-8')) + 1  # +1 for newline

            # Send periodic progress (every 100 lines)
            if line_number % 100 == 0:
                yield ("progress", {"percent": percent, "lines_processed": line_number})

            # Check for match
            match = regex.search(line)
            if match:
                matches_found += 1
                yield ("match", {
                    "line_number": line_number,
                    "line_content": line,
                    "match_start": match.start(),
                    "match_end": match.end()
                })

                if matches_found >= max_matches:
                    yield ("info", {"message": f"Reached max matches limit ({max_matches})"})
                    break

        # Send done event
        yield ("done", {
            "matches_found": matches_found,
            "lines_processed": line_number if 'line_number' in dir() else 0,
            "total_size": total_size
        })

    except FileNotFoundError:
        yield ("error", {"message": f"File not found: {file_path}", "type": "FileNotFoundError"})
    except Exception as e:
        yield ("error", {"message": str(e), "type": type(e).__name__})


@router.get("/file/{path:path}")
async def stream_file(
    path: str,
    query: str = Query(None, description="Optional search query for grep results"),
    chunk_size: int = Query(8192, ge=1024, le=1048576, description="Chunk size in bytes (1KB-1MB)")
):
    """
    Stream file content in chunks via SSE.

    - If query is provided, stream grep results
    - Otherwise stream file content in chunks
    - Send progress events during streaming

    SSE Event Types:
    - progress: {"percent": int, "bytes_read": int}
    - chunk: {"content": str} (file content mode)
    - match: {"line_number": int, "line_content": str, ...} (grep mode)
    - done: {"total_bytes": int, ...}
    - error: {"message": str, "type": str}
    """
    sandbox = get_sandbox()

    # Validate path is within sandbox
    try:
        validated_path = sandbox.validate_path(path)
    except PathTraversalError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Check file exists
    if not validated_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not validated_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")

    # Get file size
    total_size = validated_path.stat().st_size

    # Choose streaming mode
    if query:
        events = stream_grep_events(validated_path, query, chunk_size, total_size)
    else:
        events = stream_file_events(validated_path, chunk_size, total_size)

    return StreamingResponse(
        sse_generator(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/search/{path:path}")
async def stream_search(
    path: str,
    pattern: str = Query(..., description="Regex pattern to search for"),
    max_matches: int = Query(100, ge=1, le=1000, description="Maximum matches to return")
):
    """
    Stream search results as they are found.

    Searches the file line-by-line and streams matches via SSE.

    SSE Event Types:
    - progress: {"percent": int, "lines_processed": int}
    - match: {"line_number": int, "line_content": str, "match_start": int, "match_end": int}
    - info: {"message": str} (e.g., when max matches reached)
    - done: {"matches_found": int, "lines_processed": int, "total_size": int}
    - error: {"message": str, "type": str}
    """
    sandbox = get_sandbox()

    # Validate path is within sandbox
    try:
        validated_path = sandbox.validate_path(path)
    except PathTraversalError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Check file exists
    if not validated_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not validated_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")

    events = stream_search_events(validated_path, pattern, max_matches)

    return StreamingResponse(
        sse_generator(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
