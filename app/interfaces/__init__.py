"""
Interface definitions for the filesystem-agent-showcase application.

This module provides abstract base classes (ABCs) that define the contracts
for the major components in the system. Using interfaces enables:
- Better testability through mock implementations
- Clear documentation of component capabilities
- Type safety with static type checkers
- Dependency injection and substitution

Available Interfaces:
    IExecutor: Command execution interface
    ICacheBackend: Cache storage backend interface
    IFileStateTracker: File change detection interface
    IContentCache: File content caching interface
    ISearchCache: Search result caching interface
    ICacheManager: Unified cache manager interface
    IToolOrchestrator: Tool execution orchestration interface
    IToolRegistry: Tool definition registry interface
"""

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

__all__ = [
    "IExecutor",
    "ICacheBackend",
    "IFileStateTracker",
    "IContentCache",
    "ISearchCache",
    "ICacheManager",
    "IToolOrchestrator",
    "IToolRegistry",
]
