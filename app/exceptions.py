"""
Custom exception hierarchy for Filesystem Agent.

Provides structured error handling with proper HTTP status codes and error codes.
"""

from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class FilesystemAgentException(Exception):
    """Base exception for all agent errors"""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SecurityException(FilesystemAgentException):
    """Security-related errors"""
    status_code = 403
    error_code = "SECURITY_ERROR"


class PathTraversalException(SecurityException):
    """Path traversal attempt detected"""
    error_code = "PATH_TRAVERSAL"


class CommandNotAllowedException(SecurityException):
    """Command not in whitelist"""
    error_code = "COMMAND_NOT_ALLOWED"


class ExecutionException(FilesystemAgentException):
    """Command execution errors"""
    status_code = 500
    error_code = "EXECUTION_ERROR"


class TimeoutException(ExecutionException):
    """Command timeout"""
    error_code = "COMMAND_TIMEOUT"


class OutputSizeException(ExecutionException):
    """Output too large"""
    error_code = "OUTPUT_TOO_LARGE"


class ValidationException(FilesystemAgentException):
    """Input validation errors"""
    status_code = 400
    error_code = "VALIDATION_ERROR"


class SessionException(FilesystemAgentException):
    """Session-related errors"""
    status_code = 404
    error_code = "SESSION_ERROR"


class SessionNotFoundException(SessionException):
    """Session not found"""
    error_code = "SESSION_NOT_FOUND"


class CacheException(FilesystemAgentException):
    """Cache-related errors"""
    status_code = 500
    error_code = "CACHE_ERROR"


# Global exception handler
async def agent_exception_handler(
    request: Request,
    exc: FilesystemAgentException
) -> JSONResponse:
    """
    Global exception handler for FilesystemAgentException and its subclasses.

    Returns a JSON response with error code, message, and details.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        }
    )
