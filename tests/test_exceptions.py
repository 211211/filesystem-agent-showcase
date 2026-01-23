"""
Unit tests for custom exception hierarchy.

Tests exception creation, attributes, and the global exception handler.
"""

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from unittest.mock import MagicMock

from app.exceptions import (
    FilesystemAgentException,
    SecurityException,
    PathTraversalException,
    CommandNotAllowedException,
    ExecutionException,
    TimeoutException,
    OutputSizeException,
    ValidationException,
    SessionException,
    SessionNotFoundException,
    CacheException,
    agent_exception_handler,
)


class TestFilesystemAgentException:
    """Test base exception class."""

    def test_base_exception_creation(self):
        """Test creating base exception with message."""
        exc = FilesystemAgentException("Test error")
        assert exc.message == "Test error"
        assert exc.details == {}
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert str(exc) == "Test error"

    def test_base_exception_with_details(self):
        """Test creating base exception with details."""
        details = {"key": "value", "count": 42}
        exc = FilesystemAgentException("Test error", details=details)
        assert exc.message == "Test error"
        assert exc.details == details
        assert exc.details["key"] == "value"
        assert exc.details["count"] == 42


class TestSecurityExceptions:
    """Test security-related exceptions."""

    def test_security_exception(self):
        """Test SecurityException attributes."""
        exc = SecurityException("Security violation")
        assert exc.status_code == 403
        assert exc.error_code == "SECURITY_ERROR"
        assert exc.message == "Security violation"

    def test_path_traversal_exception(self):
        """Test PathTraversalException attributes."""
        exc = PathTraversalException("Path traversal detected")
        assert exc.status_code == 403
        assert exc.error_code == "PATH_TRAVERSAL"
        assert exc.message == "Path traversal detected"

    def test_path_traversal_with_details(self):
        """Test PathTraversalException with details."""
        details = {"path": "/etc/passwd", "root": "/data"}
        exc = PathTraversalException("Path outside root", details=details)
        assert exc.details == details

    def test_command_not_allowed_exception(self):
        """Test CommandNotAllowedException attributes."""
        exc = CommandNotAllowedException("Command not allowed")
        assert exc.status_code == 403
        assert exc.error_code == "COMMAND_NOT_ALLOWED"
        assert exc.message == "Command not allowed"


class TestExecutionExceptions:
    """Test execution-related exceptions."""

    def test_execution_exception(self):
        """Test ExecutionException attributes."""
        exc = ExecutionException("Execution failed")
        assert exc.status_code == 500
        assert exc.error_code == "EXECUTION_ERROR"
        assert exc.message == "Execution failed"

    def test_timeout_exception(self):
        """Test TimeoutException attributes."""
        exc = TimeoutException("Command timed out")
        assert exc.status_code == 500
        assert exc.error_code == "COMMAND_TIMEOUT"
        assert exc.message == "Command timed out"

    def test_timeout_with_details(self):
        """Test TimeoutException with details."""
        details = {"timeout": 30, "command": "grep"}
        exc = TimeoutException("Timeout after 30s", details=details)
        assert exc.details["timeout"] == 30
        assert exc.details["command"] == "grep"

    def test_output_size_exception(self):
        """Test OutputSizeException attributes."""
        exc = OutputSizeException("Output too large")
        assert exc.status_code == 500
        assert exc.error_code == "OUTPUT_TOO_LARGE"
        assert exc.message == "Output too large"


class TestValidationException:
    """Test validation exception."""

    def test_validation_exception(self):
        """Test ValidationException attributes."""
        exc = ValidationException("Invalid input")
        assert exc.status_code == 400
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.message == "Invalid input"

    def test_validation_with_details(self):
        """Test ValidationException with field details."""
        details = {"field": "path", "value": "", "reason": "empty"}
        exc = ValidationException("Path cannot be empty", details=details)
        assert exc.details["field"] == "path"
        assert exc.details["reason"] == "empty"


class TestSessionExceptions:
    """Test session-related exceptions."""

    def test_session_exception(self):
        """Test SessionException attributes."""
        exc = SessionException("Session error")
        assert exc.status_code == 404
        assert exc.error_code == "SESSION_ERROR"
        assert exc.message == "Session error"

    def test_session_not_found_exception(self):
        """Test SessionNotFoundException attributes."""
        exc = SessionNotFoundException("Session not found")
        assert exc.status_code == 404
        assert exc.error_code == "SESSION_NOT_FOUND"
        assert exc.message == "Session not found"

    def test_session_not_found_with_id(self):
        """Test SessionNotFoundException with session ID."""
        details = {"session_id": "abc-123"}
        exc = SessionNotFoundException("Session not found", details=details)
        assert exc.details["session_id"] == "abc-123"


class TestCacheException:
    """Test cache-related exception."""

    def test_cache_exception(self):
        """Test CacheException attributes."""
        exc = CacheException("Cache error")
        assert exc.status_code == 500
        assert exc.error_code == "CACHE_ERROR"
        assert exc.message == "Cache error"

    def test_cache_exception_with_details(self):
        """Test CacheException with details."""
        details = {"operation": "get", "key": "test-key"}
        exc = CacheException("Cache operation failed", details=details)
        assert exc.details["operation"] == "get"
        assert exc.details["key"] == "test-key"


class TestExceptionHandler:
    """Test the global exception handler."""

    @pytest.mark.asyncio
    async def test_handler_base_exception(self):
        """Test handler with base FilesystemAgentException."""
        exc = FilesystemAgentException("Test error")
        request = MagicMock(spec=Request)

        response = await agent_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        assert response.body is not None

        # Parse response body
        import json
        body = json.loads(response.body)
        assert body["error"] == "INTERNAL_ERROR"
        assert body["message"] == "Test error"
        assert body["details"] == {}

    @pytest.mark.asyncio
    async def test_handler_path_traversal(self):
        """Test handler with PathTraversalException."""
        details = {"path": "../etc/passwd"}
        exc = PathTraversalException("Path traversal detected", details=details)
        request = MagicMock(spec=Request)

        response = await agent_exception_handler(request, exc)

        assert response.status_code == 403
        import json
        body = json.loads(response.body)
        assert body["error"] == "PATH_TRAVERSAL"
        assert body["message"] == "Path traversal detected"
        assert body["details"]["path"] == "../etc/passwd"

    @pytest.mark.asyncio
    async def test_handler_validation_exception(self):
        """Test handler with ValidationException."""
        details = {"field": "path", "reason": "empty"}
        exc = ValidationException("Path cannot be empty", details=details)
        request = MagicMock(spec=Request)

        response = await agent_exception_handler(request, exc)

        assert response.status_code == 400
        import json
        body = json.loads(response.body)
        assert body["error"] == "VALIDATION_ERROR"
        assert body["message"] == "Path cannot be empty"
        assert body["details"]["field"] == "path"

    @pytest.mark.asyncio
    async def test_handler_timeout_exception(self):
        """Test handler with TimeoutException."""
        details = {"timeout": 30, "command": "find"}
        exc = TimeoutException("Command timed out after 30s", details=details)
        request = MagicMock(spec=Request)

        response = await agent_exception_handler(request, exc)

        assert response.status_code == 500
        import json
        body = json.loads(response.body)
        assert body["error"] == "COMMAND_TIMEOUT"
        assert body["message"] == "Command timed out after 30s"
        assert body["details"]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_handler_session_not_found(self):
        """Test handler with SessionNotFoundException."""
        details = {"session_id": "test-123"}
        exc = SessionNotFoundException("Session not found", details=details)
        request = MagicMock(spec=Request)

        response = await agent_exception_handler(request, exc)

        assert response.status_code == 404
        import json
        body = json.loads(response.body)
        assert body["error"] == "SESSION_NOT_FOUND"
        assert body["message"] == "Session not found"
        assert body["details"]["session_id"] == "test-123"


class TestExceptionInheritance:
    """Test exception inheritance hierarchy."""

    def test_all_inherit_from_base(self):
        """Test that all custom exceptions inherit from FilesystemAgentException."""
        exceptions = [
            SecurityException,
            PathTraversalException,
            CommandNotAllowedException,
            ExecutionException,
            TimeoutException,
            OutputSizeException,
            ValidationException,
            SessionException,
            SessionNotFoundException,
            CacheException,
        ]

        for exc_class in exceptions:
            exc = exc_class("Test")
            assert isinstance(exc, FilesystemAgentException)
            assert isinstance(exc, Exception)

    def test_security_exceptions_inherit_from_security(self):
        """Test that security exceptions inherit from SecurityException."""
        exc1 = PathTraversalException("Test")
        exc2 = CommandNotAllowedException("Test")

        assert isinstance(exc1, SecurityException)
        assert isinstance(exc2, SecurityException)

    def test_execution_exceptions_inherit_from_execution(self):
        """Test that execution exceptions inherit from ExecutionException."""
        exc1 = TimeoutException("Test")
        exc2 = OutputSizeException("Test")

        assert isinstance(exc1, ExecutionException)
        assert isinstance(exc2, ExecutionException)

    def test_session_not_found_inherits_from_session(self):
        """Test that SessionNotFoundException inherits from SessionException."""
        exc = SessionNotFoundException("Test")
        assert isinstance(exc, SessionException)


class TestStatusCodes:
    """Test that exceptions have correct HTTP status codes."""

    def test_status_codes(self):
        """Test status codes for all exceptions."""
        test_cases = [
            (FilesystemAgentException("test"), 500),
            (SecurityException("test"), 403),
            (PathTraversalException("test"), 403),
            (CommandNotAllowedException("test"), 403),
            (ExecutionException("test"), 500),
            (TimeoutException("test"), 500),
            (OutputSizeException("test"), 500),
            (ValidationException("test"), 400),
            (SessionException("test"), 404),
            (SessionNotFoundException("test"), 404),
            (CacheException("test"), 500),
        ]

        for exc, expected_status in test_cases:
            assert exc.status_code == expected_status, \
                f"{type(exc).__name__} should have status_code {expected_status}"


class TestErrorCodes:
    """Test that exceptions have correct error codes."""

    def test_error_codes(self):
        """Test error codes for all exceptions."""
        test_cases = [
            (FilesystemAgentException("test"), "INTERNAL_ERROR"),
            (SecurityException("test"), "SECURITY_ERROR"),
            (PathTraversalException("test"), "PATH_TRAVERSAL"),
            (CommandNotAllowedException("test"), "COMMAND_NOT_ALLOWED"),
            (ExecutionException("test"), "EXECUTION_ERROR"),
            (TimeoutException("test"), "COMMAND_TIMEOUT"),
            (OutputSizeException("test"), "OUTPUT_TOO_LARGE"),
            (ValidationException("test"), "VALIDATION_ERROR"),
            (SessionException("test"), "SESSION_ERROR"),
            (SessionNotFoundException("test"), "SESSION_NOT_FOUND"),
            (CacheException("test"), "CACHE_ERROR"),
        ]

        for exc, expected_code in test_cases:
            assert exc.error_code == expected_code, \
                f"{type(exc).__name__} should have error_code {expected_code}"
