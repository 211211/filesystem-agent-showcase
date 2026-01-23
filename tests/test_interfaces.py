"""
Tests to verify interface compliance of implementations.

This module ensures that all concrete implementations properly
implement their corresponding interfaces (ABCs).
"""

import pytest
from pathlib import Path

from app.interfaces.executor import IExecutor
from app.interfaces.cache import (
    ICacheBackend,
    IFileStateTracker,
    IContentCache,
    ISearchCache,
    ICacheManager,
)
from app.interfaces.orchestrator import IToolOrchestrator
from app.interfaces.registry import IToolRegistry

from app.sandbox.executor import SandboxExecutor
from app.cache.disk_cache import PersistentCache
from app.cache.file_state import FileStateTracker
from app.cache.content_cache import ContentCache
from app.cache.search_cache import SearchCache
from app.cache.cache_manager import CacheManager
from app.agent.orchestrator import ParallelToolOrchestrator
from app.repositories.tool_registry import ToolRegistry


class TestExecutorInterface:
    """Verify SandboxExecutor implements IExecutor correctly."""

    def test_sandbox_executor_is_instance_of_iexecutor(self, tmp_path: Path):
        """SandboxExecutor should be an instance of IExecutor."""
        executor = SandboxExecutor(root_path=tmp_path)
        assert isinstance(executor, IExecutor)

    def test_sandbox_executor_has_root_path_property(self, tmp_path: Path):
        """SandboxExecutor should have root_path property."""
        executor = SandboxExecutor(root_path=tmp_path)
        assert executor.root_path == tmp_path.resolve()

    def test_sandbox_executor_has_timeout_property(self, tmp_path: Path):
        """SandboxExecutor should have timeout property."""
        executor = SandboxExecutor(root_path=tmp_path, timeout=60)
        assert executor.timeout == 60

    @pytest.mark.asyncio
    async def test_sandbox_executor_has_execute_method(self, tmp_path: Path):
        """SandboxExecutor should have execute method."""
        executor = SandboxExecutor(root_path=tmp_path)
        result = await executor.execute(["ls"])
        assert hasattr(result, "success")
        assert hasattr(result, "stdout")

    @pytest.mark.asyncio
    async def test_sandbox_executor_has_execute_from_string_method(self, tmp_path: Path):
        """SandboxExecutor should have execute_from_string method."""
        executor = SandboxExecutor(root_path=tmp_path)
        result = await executor.execute_from_string("ls")
        assert hasattr(result, "success")


class TestCacheBackendInterface:
    """Verify PersistentCache implements ICacheBackend correctly."""

    def test_persistent_cache_is_instance_of_icache_backend(self, tmp_path: Path):
        """PersistentCache should be an instance of ICacheBackend."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(cache, ICacheBackend)
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_persistent_cache_has_get_method(self, tmp_path: Path):
        """PersistentCache should have get method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            result = await cache.get("nonexistent")
            assert result is None
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_persistent_cache_has_set_method(self, tmp_path: Path):
        """PersistentCache should have set method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            await cache.set("key", "value")
            result = await cache.get("key")
            assert result == "value"
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_persistent_cache_has_delete_method(self, tmp_path: Path):
        """PersistentCache should have delete method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            await cache.set("key", "value")
            deleted = await cache.delete("key")
            assert deleted is True
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_persistent_cache_has_clear_method(self, tmp_path: Path):
        """PersistentCache should have clear method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            await cache.set("key", "value")
            await cache.clear()
            result = await cache.get("key")
            assert result is None
        finally:
            cache.close()

    def test_persistent_cache_has_stats_method(self, tmp_path: Path):
        """PersistentCache should have stats method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            stats = cache.stats()
            assert "size" in stats
            assert "volume" in stats
            assert "directory" in stats
        finally:
            cache.close()


class TestFileStateTrackerInterface:
    """Verify FileStateTracker implements IFileStateTracker correctly."""

    def test_file_state_tracker_is_instance_of_interface(self, tmp_path: Path):
        """FileStateTracker should be an instance of IFileStateTracker."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            assert isinstance(tracker, IFileStateTracker)
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_file_state_tracker_has_get_state_method(self, tmp_path: Path):
        """FileStateTracker should have get_state method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            test_file = tmp_path / "test.txt"
            test_file.write_text("test")
            state = await tracker.get_state(test_file)
            # First call returns None (no cached state)
            assert state is None
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_file_state_tracker_has_update_state_method(self, tmp_path: Path):
        """FileStateTracker should have update_state method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            test_file = tmp_path / "test.txt"
            test_file.write_text("test")
            state = await tracker.update_state(test_file)
            assert state is not None
            assert hasattr(state, "mtime")
            assert hasattr(state, "size")
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_file_state_tracker_has_is_stale_method(self, tmp_path: Path):
        """FileStateTracker should have is_stale method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            test_file = tmp_path / "test.txt"
            test_file.write_text("test")
            # First call should be stale (no cached state)
            is_stale = await tracker.is_stale(test_file)
            assert is_stale is True
        finally:
            cache.close()


class TestContentCacheInterface:
    """Verify ContentCache implements IContentCache correctly."""

    def test_content_cache_is_instance_of_interface(self, tmp_path: Path):
        """ContentCache should be an instance of IContentCache."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            content_cache = ContentCache(cache, tracker)
            assert isinstance(content_cache, IContentCache)
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_content_cache_has_get_content_method(self, tmp_path: Path):
        """ContentCache should have get_content method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            content_cache = ContentCache(cache, tracker)

            test_file = tmp_path / "test.txt"
            test_file.write_text("hello world")

            async def loader(path: Path) -> str:
                return path.read_text()

            content = await content_cache.get_content(test_file, loader)
            assert content == "hello world"
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_content_cache_has_invalidate_method(self, tmp_path: Path):
        """ContentCache should have invalidate method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            content_cache = ContentCache(cache, tracker)

            test_file = tmp_path / "test.txt"
            test_file.write_text("content")

            # Should not raise
            await content_cache.invalidate(test_file)
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_content_cache_has_invalidate_directory_method(self, tmp_path: Path):
        """ContentCache should have invalidate_directory method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            content_cache = ContentCache(cache, tracker)

            count = await content_cache.invalidate_directory(tmp_path)
            assert isinstance(count, int)
        finally:
            cache.close()


class TestSearchCacheInterface:
    """Verify SearchCache implements ISearchCache correctly."""

    def test_search_cache_is_instance_of_interface(self, tmp_path: Path):
        """SearchCache should be an instance of ISearchCache."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            search_cache = SearchCache(cache, tracker)
            assert isinstance(search_cache, ISearchCache)
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_search_cache_has_get_search_result_method(self, tmp_path: Path):
        """SearchCache should have get_search_result method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            search_cache = SearchCache(cache, tracker)

            result = await search_cache.get_search_result(
                operation="grep",
                pattern="test",
                scope=tmp_path,
                options={}
            )
            assert result is None  # No cached result
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_search_cache_has_set_search_result_method(self, tmp_path: Path):
        """SearchCache should have set_search_result method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            search_cache = SearchCache(cache, tracker)

            # Should not raise
            await search_cache.set_search_result(
                operation="grep",
                pattern="test",
                scope=tmp_path,
                options={},
                result="test result"
            )
        finally:
            cache.close()

    @pytest.mark.asyncio
    async def test_search_cache_has_invalidate_pattern_method(self, tmp_path: Path):
        """SearchCache should have invalidate_pattern method."""
        cache = PersistentCache(cache_dir=str(tmp_path / "cache"))
        try:
            tracker = FileStateTracker(cache)
            search_cache = SearchCache(cache, tracker)

            deleted = await search_cache.invalidate_pattern(
                operation="grep",
                pattern="test",
                scope=tmp_path,
                options={}
            )
            assert isinstance(deleted, bool)
        finally:
            cache.close()


class TestCacheManagerInterface:
    """Verify CacheManager implements ICacheManager correctly."""

    def test_cache_manager_is_instance_of_interface(self, tmp_path: Path):
        """CacheManager should be an instance of ICacheManager."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(manager, ICacheManager)
        finally:
            manager.close()

    def test_cache_manager_has_persistent_cache_property(self, tmp_path: Path):
        """CacheManager should have persistent_cache property."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(manager.persistent_cache, ICacheBackend)
        finally:
            manager.close()

    def test_cache_manager_has_file_state_tracker_property(self, tmp_path: Path):
        """CacheManager should have file_state_tracker property."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(manager.file_state_tracker, IFileStateTracker)
        finally:
            manager.close()

    def test_cache_manager_has_content_cache_property(self, tmp_path: Path):
        """CacheManager should have content_cache property."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(manager.content_cache, IContentCache)
        finally:
            manager.close()

    def test_cache_manager_has_search_cache_property(self, tmp_path: Path):
        """CacheManager should have search_cache property."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            assert isinstance(manager.search_cache, ISearchCache)
        finally:
            manager.close()

    def test_cache_manager_has_stats_method(self, tmp_path: Path):
        """CacheManager should have stats method."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            stats = manager.stats()
            assert "enabled" in stats
            assert "disk_cache" in stats
        finally:
            manager.close()

    @pytest.mark.asyncio
    async def test_cache_manager_has_clear_all_method(self, tmp_path: Path):
        """CacheManager should have clear_all method."""
        manager = CacheManager(cache_dir=str(tmp_path / "cache"))
        try:
            # Should not raise
            await manager.clear_all()
        finally:
            manager.close()


class TestOrchestratorInterface:
    """Verify ParallelToolOrchestrator implements IToolOrchestrator correctly."""

    def test_orchestrator_is_instance_of_interface(self, tmp_path: Path):
        """ParallelToolOrchestrator should be an instance of IToolOrchestrator."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor)
        assert isinstance(orchestrator, IToolOrchestrator)

    def test_orchestrator_has_max_concurrent_property(self, tmp_path: Path):
        """ParallelToolOrchestrator should have max_concurrent property."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor, max_concurrent=10)
        assert orchestrator.max_concurrent == 10

    @pytest.mark.asyncio
    async def test_orchestrator_has_execute_parallel_method(self, tmp_path: Path):
        """ParallelToolOrchestrator should have execute_parallel method."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor)
        results = await orchestrator.execute_parallel([])
        assert results == []

    @pytest.mark.asyncio
    async def test_orchestrator_has_execute_sequential_method(self, tmp_path: Path):
        """ParallelToolOrchestrator should have execute_sequential method."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor)
        results = await orchestrator.execute_sequential([])
        assert results == []

    @pytest.mark.asyncio
    async def test_orchestrator_has_execute_with_strategy_method(self, tmp_path: Path):
        """ParallelToolOrchestrator should have execute_with_strategy method."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor)
        results = await orchestrator.execute_with_strategy([])
        assert results == []

    def test_orchestrator_has_analyze_dependencies_method(self, tmp_path: Path):
        """ParallelToolOrchestrator should have analyze_dependencies method."""
        executor = SandboxExecutor(root_path=tmp_path)
        orchestrator = ParallelToolOrchestrator(sandbox=executor)
        groups = orchestrator.analyze_dependencies([])
        assert groups == []


class TestToolRegistryInterface:
    """Verify ToolRegistry implements IToolRegistry correctly."""

    def test_tool_registry_is_instance_of_interface(self):
        """ToolRegistry should be an instance of IToolRegistry."""
        registry = ToolRegistry()
        assert isinstance(registry, IToolRegistry)

    def test_tool_registry_has_register_method(self):
        """ToolRegistry should have register method."""
        from app.repositories.tool_registry import ToolDefinition, ToolParameter

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test",
            description="Test tool",
            parameters=[ToolParameter("arg", "string", "An argument")],
            builder=lambda args: ["echo", args.get("arg", "")]
        )
        # Should not raise
        registry.register(tool)
        assert "test" in registry

    def test_tool_registry_has_unregister_method(self):
        """ToolRegistry should have unregister method."""
        from app.repositories.tool_registry import ToolDefinition, ToolParameter

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test",
            description="Test tool",
            parameters=[ToolParameter("arg", "string", "An argument")],
            builder=lambda args: ["echo", args.get("arg", "")]
        )
        registry.register(tool)
        result = registry.unregister("test")
        assert result is True

    def test_tool_registry_has_get_method(self):
        """ToolRegistry should have get method."""
        registry = ToolRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_tool_registry_has_list_all_method(self):
        """ToolRegistry should have list_all method."""
        registry = ToolRegistry()
        tools = registry.list_all()
        assert isinstance(tools, list)

    def test_tool_registry_has_list_names_method(self):
        """ToolRegistry should have list_names method."""
        registry = ToolRegistry()
        names = registry.list_names()
        assert isinstance(names, list)

    def test_tool_registry_has_to_openai_format_method(self):
        """ToolRegistry should have to_openai_format method."""
        registry = ToolRegistry()
        format_list = registry.to_openai_format()
        assert isinstance(format_list, list)

    def test_tool_registry_has_build_command_method(self):
        """ToolRegistry should have build_command method."""
        from app.repositories.tool_registry import ToolDefinition, ToolParameter

        registry = ToolRegistry()
        tool = ToolDefinition(
            name="echo",
            description="Echo tool",
            parameters=[ToolParameter("message", "string", "Message to echo")],
            builder=lambda args: ["echo", args.get("message", "")]
        )
        registry.register(tool)
        command = registry.build_command("echo", {"message": "hello"})
        assert command == ["echo", "hello"]

    def test_tool_registry_has_is_cacheable_method(self):
        """ToolRegistry should have is_cacheable method."""
        registry = ToolRegistry()
        result = registry.is_cacheable("nonexistent")
        assert result is False

    def test_tool_registry_has_get_cache_ttl_method(self):
        """ToolRegistry should have get_cache_ttl method."""
        registry = ToolRegistry()
        result = registry.get_cache_ttl("nonexistent")
        assert result is None
