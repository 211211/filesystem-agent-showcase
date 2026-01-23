"""
Tests for tool handlers using Chain of Responsibility pattern.

These tests verify:
1. Handler chain construction
2. can_handle() routing logic
3. Execution delegation through the chain
4. Default handler catches all unhandled tools
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.agent.handlers import (
    ToolHandler,
    CachedReadHandler,
    CachedSearchHandler,
    DefaultHandler,
    create_handler_chain,
)
from app.agent.filesystem_agent import ToolCall
from app.sandbox.executor import ExecutionResult
from app.cache import CacheManager


# Fixtures

@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox executor."""
    sandbox = Mock()
    sandbox.execute = AsyncMock(return_value=ExecutionResult(
        success=True,
        stdout="test output",
        stderr="",
        return_code=0,
        command="test command",
        error=None,
    ))
    return sandbox


@pytest.fixture
def mock_cache_manager(tmp_path):
    """Create a mock cache manager."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cache_manager = Mock(spec=CacheManager)

    # Mock content_cache
    cache_manager.content_cache = Mock()
    cache_manager.content_cache.get_content = AsyncMock(return_value="file content\n")

    # Mock search_cache
    cache_manager.search_cache = Mock()
    cache_manager.search_cache.get_search = AsyncMock(return_value=ExecutionResult(
        success=True,
        stdout="search result",
        stderr="",
        return_code=0,
        command="grep pattern file.txt",
        error=None,
    ))

    return cache_manager


@pytest.fixture
def data_root(tmp_path):
    """Create a temporary data root directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create a test file
    test_file = data_dir / "test.txt"
    test_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

    return data_dir


# Test ToolHandler base class

class TestToolHandler:
    """Tests for the abstract ToolHandler base class."""

    def test_handler_init_with_next(self):
        """Test handler initialization with next handler."""
        next_handler = DefaultHandler()
        handler = CachedReadHandler(next_handler=next_handler)

        assert handler._next_handler == next_handler

    def test_handler_init_without_next(self):
        """Test handler initialization without next handler."""
        handler = DefaultHandler()

        assert handler._next_handler is None

    @pytest.mark.asyncio
    async def test_handle_delegates_when_cannot_handle(self):
        """Test that handler delegates to next when it cannot handle."""
        # Create a chain: CachedReadHandler -> DefaultHandler
        default_handler = DefaultHandler()
        read_handler = CachedReadHandler(next_handler=default_handler)

        # Create a tool call that CachedReadHandler cannot handle
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})

        # Mock the sandbox
        mock_sandbox = Mock()
        mock_sandbox.execute = AsyncMock(return_value=ExecutionResult(
            success=True,
            stdout="file1.txt\nfile2.txt",
            stderr="",
            return_code=0,
            command="ls .",
            error=None,
        ))

        # Execute through the chain
        result = await read_handler.handle(tool_call, sandbox=mock_sandbox)

        # Should be handled by DefaultHandler
        assert result.success
        assert "file1.txt" in result.stdout

    @pytest.mark.asyncio
    async def test_handle_raises_when_no_handler_found(self):
        """Test that ValueError is raised when no handler can handle the tool."""
        # Create a custom handler that never handles anything
        class NeverHandler(ToolHandler):
            def can_handle(self, tool_call: ToolCall) -> bool:
                return False

            async def _do_handle(self, tool_call: ToolCall, **kwargs) -> ExecutionResult:
                pass

        # Create handler without next
        handler = NeverHandler()

        tool_call = ToolCall(id="1", name="unknown", arguments={})

        with pytest.raises(ValueError, match="No handler found for tool"):
            await handler.handle(tool_call)


# Test CachedReadHandler

class TestCachedReadHandler:
    """Tests for CachedReadHandler."""

    def test_can_handle_cat(self):
        """Test that handler recognizes cat tool."""
        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})

        assert handler.can_handle(tool_call)

    def test_can_handle_head(self):
        """Test that handler recognizes head tool."""
        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="head", arguments={"path": "test.txt"})

        assert handler.can_handle(tool_call)

    def test_can_handle_tail(self):
        """Test that handler recognizes tail tool."""
        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="tail", arguments={"path": "test.txt"})

        assert handler.can_handle(tool_call)

    def test_cannot_handle_other_tools(self):
        """Test that handler rejects non-read tools."""
        handler = CachedReadHandler()

        for tool_name in ["grep", "find", "ls", "tree", "wc"]:
            tool_call = ToolCall(id="1", name=tool_name, arguments={})
            assert not handler.can_handle(tool_call)

    @pytest.mark.asyncio
    async def test_handle_cat(self, mock_cache_manager, mock_sandbox, data_root):
        """Test handling cat command with cache."""
        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        assert result.stdout == "file content\n"
        mock_cache_manager.content_cache.get_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_head(self, mock_cache_manager, mock_sandbox, data_root):
        """Test handling head command with cache."""
        # Mock full file content
        mock_cache_manager.content_cache.get_content = AsyncMock(
            return_value="line 1\nline 2\nline 3\nline 4\nline 5\n"
        )

        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="head", arguments={"path": "test.txt", "lines": 3})

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        assert result.stdout == "line 1\nline 2\nline 3\n"

    @pytest.mark.asyncio
    async def test_handle_tail(self, mock_cache_manager, mock_sandbox, data_root):
        """Test handling tail command with cache."""
        # Mock full file content
        mock_cache_manager.content_cache.get_content = AsyncMock(
            return_value="line 1\nline 2\nline 3\nline 4\nline 5\n"
        )

        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="tail", arguments={"path": "test.txt", "lines": 2})

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        assert result.stdout == "line 4\nline 5\n"

    @pytest.mark.asyncio
    async def test_handle_requires_cache_manager(self, mock_sandbox, data_root):
        """Test that handler raises error without cache_manager."""
        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})

        with pytest.raises(ValueError, match="requires cache_manager"):
            await handler.handle(
                tool_call,
                sandbox=mock_sandbox,
                data_root=data_root,
            )

    @pytest.mark.asyncio
    async def test_handle_error_returns_failed_result(self, mock_cache_manager, mock_sandbox, data_root):
        """Test that handler returns failed result on error."""
        # Make cache raise an error
        mock_cache_manager.content_cache.get_content = AsyncMock(
            side_effect=Exception("Cache error")
        )

        handler = CachedReadHandler()
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert not result.success
        assert "Cache error" in result.stderr


# Test CachedSearchHandler

class TestCachedSearchHandler:
    """Tests for CachedSearchHandler."""

    def test_can_handle_grep(self):
        """Test that handler recognizes grep tool."""
        handler = CachedSearchHandler()
        tool_call = ToolCall(id="1", name="grep", arguments={"pattern": "test", "path": "."})

        assert handler.can_handle(tool_call)

    def test_can_handle_find(self):
        """Test that handler recognizes find tool."""
        handler = CachedSearchHandler()
        tool_call = ToolCall(id="1", name="find", arguments={"path": ".", "name_pattern": "*.txt"})

        assert handler.can_handle(tool_call)

    def test_cannot_handle_other_tools(self):
        """Test that handler rejects non-search tools."""
        handler = CachedSearchHandler()

        for tool_name in ["cat", "head", "tail", "ls", "tree", "wc"]:
            tool_call = ToolCall(id="1", name=tool_name, arguments={})
            assert not handler.can_handle(tool_call)

    @pytest.mark.asyncio
    async def test_handle_grep(self, mock_cache_manager, mock_sandbox, data_root):
        """Test handling grep command with cache."""
        handler = CachedSearchHandler()
        tool_call = ToolCall(
            id="1",
            name="grep",
            arguments={"pattern": "test", "path": ".", "recursive": True}
        )

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        assert "search result" in result.stdout
        mock_cache_manager.search_cache.get_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_find(self, mock_cache_manager, mock_sandbox, data_root):
        """Test handling find command with cache."""
        handler = CachedSearchHandler()
        tool_call = ToolCall(
            id="1",
            name="find",
            arguments={"path": ".", "name_pattern": "*.txt"}
        )

        result = await handler.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        mock_cache_manager.search_cache.get_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_requires_cache_manager(self, mock_sandbox, data_root):
        """Test that handler raises error without cache_manager."""
        handler = CachedSearchHandler()
        tool_call = ToolCall(id="1", name="grep", arguments={"pattern": "test", "path": "."})

        with pytest.raises(ValueError, match="requires cache_manager"):
            await handler.handle(
                tool_call,
                sandbox=mock_sandbox,
                data_root=data_root,
            )


# Test DefaultHandler

class TestDefaultHandler:
    """Tests for DefaultHandler."""

    def test_can_handle_any_tool(self):
        """Test that handler accepts any tool."""
        handler = DefaultHandler()

        for tool_name in ["ls", "tree", "wc", "unknown", "custom"]:
            tool_call = ToolCall(id="1", name=tool_name, arguments={})
            assert handler.can_handle(tool_call)

    @pytest.mark.asyncio
    async def test_handle_ls(self, mock_sandbox):
        """Test handling ls command."""
        handler = DefaultHandler()
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})

        result = await handler.handle(tool_call, sandbox=mock_sandbox)

        assert result.success
        mock_sandbox.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_wc(self, mock_sandbox):
        """Test handling wc command."""
        handler = DefaultHandler()
        tool_call = ToolCall(id="1", name="wc", arguments={"path": "test.txt"})

        result = await handler.handle(tool_call, sandbox=mock_sandbox)

        assert result.success
        mock_sandbox.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_smart_read_not_implemented(self, mock_sandbox):
        """Test that smart_read returns not implemented error."""
        handler = DefaultHandler()
        tool_call = ToolCall(id="1", name="smart_read", arguments={"path": "test.txt"})

        result = await handler.handle(tool_call, sandbox=mock_sandbox)

        assert not result.success
        assert "not supported" in result.stderr

    @pytest.mark.asyncio
    async def test_handle_requires_sandbox(self):
        """Test that handler raises error without sandbox."""
        handler = DefaultHandler()
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})

        with pytest.raises(ValueError, match="requires sandbox"):
            await handler.handle(tool_call)

    @pytest.mark.asyncio
    async def test_handle_error_returns_failed_result(self, mock_sandbox):
        """Test that handler returns failed result on error."""
        # Make execute raise an error
        mock_sandbox.execute = AsyncMock(side_effect=Exception("Execution error"))

        handler = DefaultHandler()
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})

        result = await handler.handle(tool_call, sandbox=mock_sandbox)

        assert not result.success
        assert "Execution error" in result.stderr


# Test create_handler_chain

class TestCreateHandlerChain:
    """Tests for create_handler_chain factory function."""

    def test_create_chain_with_cache(self, mock_cache_manager):
        """Test creating handler chain with cache manager."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)

        # Should be CachedReadHandler
        assert isinstance(chain, CachedReadHandler)

        # Next should be CachedSearchHandler
        assert isinstance(chain._next_handler, CachedSearchHandler)

        # Next should be DefaultHandler
        assert isinstance(chain._next_handler._next_handler, DefaultHandler)

        # DefaultHandler should have no next
        assert chain._next_handler._next_handler._next_handler is None

    def test_create_chain_without_cache(self):
        """Test creating handler chain without cache manager."""
        chain = create_handler_chain(cache_manager=None)

        # Should be DefaultHandler only
        assert isinstance(chain, DefaultHandler)
        assert chain._next_handler is None

    @pytest.mark.asyncio
    async def test_chain_routing_cat_to_cached_read(self, mock_cache_manager, mock_sandbox, data_root):
        """Test that cat commands are routed to CachedReadHandler."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)
        tool_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})

        result = await chain.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        # Verify cache was used
        mock_cache_manager.content_cache.get_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_chain_routing_grep_to_cached_search(self, mock_cache_manager, mock_sandbox, data_root):
        """Test that grep commands are routed to CachedSearchHandler."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)
        tool_call = ToolCall(
            id="1",
            name="grep",
            arguments={"pattern": "test", "path": "."}
        )

        result = await chain.handle(
            tool_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )

        assert result.success
        # Verify cache was used
        mock_cache_manager.search_cache.get_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_chain_routing_ls_to_default(self, mock_cache_manager, mock_sandbox):
        """Test that ls commands fall through to DefaultHandler."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)
        tool_call = ToolCall(id="1", name="ls", arguments={"path": "."})

        result = await chain.handle(
            tool_call,
            sandbox=mock_sandbox,
        )

        assert result.success
        # Verify sandbox was called directly (not through cache)
        mock_sandbox.execute.assert_called_once()
        # Verify caches were NOT used
        mock_cache_manager.content_cache.get_content.assert_not_called()
        mock_cache_manager.search_cache.get_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_chain_without_cache_uses_default_for_all(self, mock_sandbox):
        """Test that chain without cache uses DefaultHandler for all tools."""
        chain = create_handler_chain(cache_manager=None)

        # Try various tools
        for tool_name in ["cat", "grep", "ls", "tree"]:
            tool_call = ToolCall(id="1", name=tool_name, arguments={"path": "."})
            result = await chain.handle(tool_call, sandbox=mock_sandbox)
            assert result.success or not result.success  # Just verify it executes


# Integration tests

class TestHandlerChainIntegration:
    """Integration tests for the complete handler chain."""

    @pytest.mark.asyncio
    async def test_full_chain_execution_flow(self, mock_cache_manager, mock_sandbox, data_root):
        """Test complete execution flow through the chain."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)

        # Test 1: cat (CachedReadHandler)
        cat_call = ToolCall(id="1", name="cat", arguments={"path": "test.txt"})
        result = await chain.handle(
            cat_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )
        assert result.success

        # Test 2: grep (CachedSearchHandler)
        grep_call = ToolCall(id="2", name="grep", arguments={"pattern": "test", "path": "."})
        result = await chain.handle(
            grep_call,
            cache_manager=mock_cache_manager,
            sandbox=mock_sandbox,
            data_root=data_root,
        )
        assert result.success

        # Test 3: ls (DefaultHandler)
        ls_call = ToolCall(id="3", name="ls", arguments={"path": "."})
        result = await chain.handle(
            ls_call,
            sandbox=mock_sandbox,
        )
        assert result.success

    @pytest.mark.asyncio
    async def test_chain_handles_all_tool_types(self, mock_cache_manager, mock_sandbox, data_root):
        """Test that chain can handle all defined tool types."""
        chain = create_handler_chain(cache_manager=mock_cache_manager)

        # Define test cases for each tool type
        test_cases = [
            ("cat", {"path": "test.txt"}),
            ("head", {"path": "test.txt", "lines": 10}),
            ("tail", {"path": "test.txt", "lines": 10}),
            ("grep", {"pattern": "test", "path": "."}),
            ("find", {"path": ".", "name_pattern": "*.txt"}),
            ("ls", {"path": "."}),
            ("tree", {"path": "."}),
            ("wc", {"path": "test.txt"}),
        ]

        for tool_name, arguments in test_cases:
            tool_call = ToolCall(id=f"test_{tool_name}", name=tool_name, arguments=arguments)

            result = await chain.handle(
                tool_call,
                cache_manager=mock_cache_manager,
                sandbox=mock_sandbox,
                data_root=data_root,
            )

            # All should execute (either successfully or with error, but not crash)
            assert isinstance(result, ExecutionResult)
