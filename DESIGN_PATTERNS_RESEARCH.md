# Nghiên Cứu Design Patterns cho Filesystem Agent Showcase

> **Tác giả**: Claude AI
> **Ngày**: 2026-01-23
> **Phiên bản dự án**: v3.0 (Multi-tier Cache System)

---

## Mục Lục

1. [Tổng Quan Dự Án](#1-tổng-quan-dự-án)
2. [Kiến Trúc Hiện Tại](#2-kiến-trúc-hiện-tại)
3. [Các Design Patterns Đã Áp Dụng](#3-các-design-patterns-đã-áp-dụng)
4. [Đề Xuất Cải Tiến với Design Patterns](#4-đề-xuất-cải-tiến-với-design-patterns)
5. [Đề Xuất DAG (Directed Acyclic Graph)](#5-đề-xuất-dag-directed-acyclic-graph)
6. [Repository Pattern](#6-repository-pattern)
7. [Factory Pattern](#7-factory-pattern)
8. [Các Patterns Bổ Sung](#8-các-patterns-bổ-sung)
9. [Lộ Trình Triển Khai](#9-lộ-trình-triển-khai)
10. [Kết Luận](#10-kết-luận)

---

## 1. Tổng Quan Dự Án

### 1.1 Mô Tả

Filesystem Agent Showcase là ứng dụng Python FastAPI minh họa cách xây dựng AI agents sử dụng filesystem/bash tools thay vì RAG pipelines truyền thống. LLM (Azure OpenAI) tự quyết định commands cần thực thi và kết quả được đưa ngược vào agentic loop.

### 1.2 Thống Kê Code

| Metric | Giá Trị |
|--------|---------|
| Tổng số dòng code | ~13,653 dòng |
| Modules chính | 29 files .py |
| Test files | 20 files |
| Cache code | ~1,741 dòng |
| Agent code | ~2,500 dòng |

### 1.3 Cấu Trúc Thư Mục

```
app/
├── main.py                    # FastAPI app entry point
├── config.py                  # Pydantic settings
├── cli.py                     # CLI commands
├── agent/                     # Core agent logic
│   ├── filesystem_agent.py    # FilesystemAgent class (840 dòng)
│   ├── orchestrator.py        # ParallelToolOrchestrator (290 dòng)
│   ├── prompts.py             # System prompts
│   ├── cache.py               # Legacy cache v2.0
│   └── tools/
│       ├── bash_tools.py      # Tool definitions
│       ├── adaptive_reader.py # Smart file reading
│       ├── file_tools.py      # File utilities
│       └── streaming.py       # SSE streaming
├── sandbox/                   # Security layer
│   ├── executor.py            # SandboxExecutor
│   └── cached_executor.py     # Cached wrapper
├── cache/                     # Multi-tier cache v3.0
│   ├── cache_manager.py       # Unified interface
│   ├── disk_cache.py          # PersistentCache
│   ├── content_cache.py       # ContentCache
│   ├── search_cache.py        # SearchCache
│   ├── file_state.py          # FileStateTracker
│   └── warmup.py              # Cache warmup
└── api/routes/                # API endpoints
    ├── chat.py                # Chat API
    ├── stream.py              # SSE streaming
    └── documents.py           # Document CRUD
```

---

## 2. Kiến Trúc Hiện Tại

### 2.1 Request Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Request                               │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Router (main.py)                        │
│  ├── POST /api/chat          → agent interaction                     │
│  ├── POST /api/chat/stream   → SSE streaming                         │
│  ├── GET /api/stream/file    → file streaming                        │
│  └── GET /api/documents      → CRUD operations                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   FilesystemAgent (core agent loop)                  │
│  ├── chat() - Blocking agentic loop                                 │
│  └── chat_stream() - Streaming với SSE events                        │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Tool Execution Layer                             │
│  ├── ParallelToolOrchestrator (orchestration strategy)              │
│  ├── SandboxExecutor (security enforcement)                          │
│  └── CachedSandboxExecutor (result caching v2.0)                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 CacheManager (v3.0 multi-tier system)                │
│  ├── ContentCache (file content với auto-invalidation)              │
│  ├── SearchCache (grep/find results với TTL)                         │
│  └── FileStateTracker (mtime, size, hash detection)                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│           subprocess.create_subprocess_exec() (command execution)    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent Loop Flow

```
User Message
    │
    ▼
[Initialize: system_prompt + history + user_message]
    │
    ▼
┌─────────────────────────────────────────────┐
│         Loop (max 10 iterations)            │
│  ┌─────────────────────────────────────┐    │
│  │ Call LLM với BASH_TOOLS definitions │    │
│  └───────────────┬─────────────────────┘    │
│                  ▼                          │
│  ┌─────────────────────────────────────┐    │
│  │ Tool Calls? ─── No ──→ Return       │    │
│  └──────┬──────────────────────────────┘    │
│         │ Yes                               │
│         ▼                                   │
│  ┌─────────────────────────────────────┐    │
│  │ Execute Tools (parallel/sequential) │    │
│  └──────┬──────────────────────────────┘    │
│         ▼                                   │
│  ┌─────────────────────────────────────┐    │
│  │ Add results to message history      │    │
│  └──────┬──────────────────────────────┘    │
│         │                                   │
│         └───────────────────────────────────┘
│
└─────────────────────────────────────────────┘
    │
    ▼
Return AgentResponse
```

### 2.3 Cache System Architecture (v3.0)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FilesystemAgent                               │
│         _cached_read_file() / _cached_search()                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CacheManager (L1)                               │
│  • Unified interface điều phối tất cả cache components              │
│  • Configuration aggregation (TTL, size limits)                      │
│  • Lifecycle management                                              │
└──────────┬──────────────┬──────────────┬────────────────────────────┘
           │              │              │
  ┌────────▼────┐  ┌──────▼──────┐  ┌───▼───────────┐
  │ContentCache │  │SearchCache  │  │FileStateTracker│
  │   (L2)      │  │   (L2)      │  │     (L2)       │
  │ File content│  │ grep/find   │  │ mtime/size/hash│
  └─────────────┘  └─────────────┘  └────────────────┘
           │              │              │
           └──────────────┬──────────────┘
                          ▼
            ┌──────────────────────────┐
            │  PersistentCache (L3)    │
            │  • DiskCache backend     │
            │  • LRU eviction          │
            │  • Async/thread-safe     │
            └──────────────────────────┘
```

---

## 3. Các Design Patterns Đã Áp Dụng

### 3.1 Patterns Hiện Có

| Pattern | Vị Trí | Đánh Giá |
|---------|--------|----------|
| **Factory** | `create_agent()` trong `filesystem_agent.py` | ⭐⭐⭐ Tốt |
| **Factory** | `CacheManager.default()` | ⭐⭐⭐ Tốt |
| **Adapter** | `PersistentCache` wraps DiskCache | ⭐⭐⭐⭐ Xuất sắc |
| **Strategy** | `ParallelToolOrchestrator` (PARALLEL/SEQUENTIAL) | ⭐⭐⭐ Tốt |
| **Decorator** | `CachedSandboxExecutor` wraps `SandboxExecutor` | ⭐⭐⭐⭐ Xuất sắc |
| **State** | `FileState` + `FileStateTracker` | ⭐⭐⭐ Tốt |
| **Cache-Aside** | `ContentCache.get_content()` | ⭐⭐⭐⭐ Xuất sắc |
| **Command** | `ToolCall` dataclass | ⭐⭐⭐ Tốt |
| **Observer/Streaming** | `chat_stream()` SSE events | ⭐⭐⭐ Tốt |

### 3.2 Điểm Mạnh

1. **Separation of Concerns rõ ràng**
   - Agent loop tách biệt khỏi execution logic
   - Tool definitions tách khỏi command builders
   - Orchestration tách khỏi executor

2. **Async-First Design**
   - Tất cả I/O operations là async
   - True parallelism với `asyncio.gather()`
   - Streaming responses qua `AsyncGenerator`

3. **Security by Design**
   - SandboxExecutor whitelist enforcement
   - Path traversal prevention
   - Timeout protection + output size limits

### 3.3 Điểm Cần Cải Thiện

1. **Tight Coupling** trong CacheManager với specific implementations
2. **Session Management** dùng in-memory dict, không có abstraction
3. **Tool Execution** logic mixed trong FilesystemAgent
4. **Error Handling** không consistent across codebase
5. **Configuration** scattered qua nhiều files

---

## 4. Đề Xuất Cải Tiến với Design Patterns

### 4.1 Tổng Quan Đề Xuất

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PROPOSED ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    DAG-based Workflow                        │    │
│  │  ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐                      │    │
│  │  │Parse│──▶│Valid│──▶│Exec │──▶│Cache│                      │    │
│  │  │ ate │   │ ate │   │ ute │   │     │                      │    │
│  │  └─────┘   └─────┘   └─────┘   └─────┘                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│  ┌───────────────────────────┼───────────────────────────────────┐  │
│  │                   Repository Layer                             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │  │
│  │  │  Session     │  │   Cache      │  │    Tool      │         │  │
│  │  │  Repository  │  │  Repository  │  │   Registry   │         │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                       │
│  ┌───────────────────────────┼───────────────────────────────────┐  │
│  │                    Factory Layer                               │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │  │
│  │  │   Agent      │  │    Cache     │  │   Handler    │         │  │
│  │  │  Factory     │  │   Factory    │  │   Factory    │         │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Đề Xuất DAG (Directed Acyclic Graph)

### 5.1 Vấn Đề Hiện Tại

Hiện tại, tool execution flow là linear và không thể hiện rõ dependencies:

```python
# Hiện tại trong filesystem_agent.py
for tool_call in tool_calls:
    result = await self._execute_tool(tool_call)
    results.append(result)
```

### 5.2 Đề Xuất DAG-based Workflow

DAG cho phép định nghĩa rõ ràng dependencies giữa các operations và tự động xác định những gì có thể chạy parallel.

#### 5.2.1 Node Definitions

```python
# app/workflow/nodes.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Set, Any, Optional
from enum import Enum

class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class WorkflowNode(ABC):
    """Base class cho tất cả workflow nodes"""
    id: str
    dependencies: Set[str] = field(default_factory=set)
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None

    @abstractmethod
    async def execute(self, context: "WorkflowContext") -> Any:
        """Execute node logic"""
        pass

    def can_run(self, completed_nodes: Set[str]) -> bool:
        """Check if all dependencies are satisfied"""
        return self.dependencies.issubset(completed_nodes)

@dataclass
class ParseNode(WorkflowNode):
    """Node để parse tool arguments"""
    tool_name: str
    raw_arguments: dict

    async def execute(self, context: "WorkflowContext") -> dict:
        # Parse và validate arguments
        return self.raw_arguments

@dataclass
class ValidateNode(WorkflowNode):
    """Node để validate security"""
    command: list[str]

    async def execute(self, context: "WorkflowContext") -> bool:
        policy = context.get("security_policy")
        policy.validate_command(self.command[0])
        for arg in self.command[1:]:
            if looks_like_path(arg):
                policy.validate_path(arg)
        return True

@dataclass
class ExecuteNode(WorkflowNode):
    """Node để execute command"""
    command: list[str]

    async def execute(self, context: "WorkflowContext") -> ExecutionResult:
        executor = context.get("executor")
        return await executor.execute(self.command)

@dataclass
class CacheNode(WorkflowNode):
    """Node để cache results"""
    cache_key: str
    ttl: Optional[int] = None

    async def execute(self, context: "WorkflowContext") -> Any:
        cache = context.get("cache_manager")
        # Get result from previous node
        result = context.get_node_result(list(self.dependencies)[0])
        await cache.set(self.cache_key, result, self.ttl)
        return result
```

#### 5.2.2 DAG Executor

```python
# app/workflow/dag_executor.py
from typing import Dict, Set, List
import asyncio
from collections import defaultdict

@dataclass
class WorkflowContext:
    """Context được share giữa các nodes"""
    data: Dict[str, Any] = field(default_factory=dict)
    node_results: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        return self.data.get(key)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get_node_result(self, node_id: str) -> Any:
        return self.node_results.get(node_id)

class DAGExecutor:
    """Executor cho DAG-based workflows"""

    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)

    def build_execution_order(
        self,
        nodes: Dict[str, WorkflowNode]
    ) -> List[Set[str]]:
        """
        Topological sort để xác định execution order.
        Returns list of sets, mỗi set có thể chạy parallel.
        """
        in_degree: Dict[str, int] = defaultdict(int)
        dependents: Dict[str, Set[str]] = defaultdict(set)

        for node_id, node in nodes.items():
            in_degree[node_id] = len(node.dependencies)
            for dep in node.dependencies:
                dependents[dep].add(node_id)

        execution_layers: List[Set[str]] = []

        # Nodes với in_degree = 0 có thể chạy đầu tiên
        ready = {
            node_id for node_id, degree in in_degree.items()
            if degree == 0
        }

        while ready:
            execution_layers.append(ready.copy())

            next_ready = set()
            for node_id in ready:
                for dependent in dependents[node_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_ready.add(dependent)

            ready = next_ready

        # Validate: tất cả nodes phải được scheduled
        scheduled = set().union(*execution_layers) if execution_layers else set()
        if scheduled != set(nodes.keys()):
            unscheduled = set(nodes.keys()) - scheduled
            raise ValueError(f"Circular dependency detected: {unscheduled}")

        return execution_layers

    async def execute(
        self,
        nodes: Dict[str, WorkflowNode],
        context: WorkflowContext
    ) -> Dict[str, Any]:
        """Execute DAG với maximum parallelism"""
        execution_layers = self.build_execution_order(nodes)
        results: Dict[str, Any] = {}

        for layer in execution_layers:
            # Execute tất cả nodes trong layer đồng thời
            tasks = [
                self._execute_node(nodes[node_id], context)
                for node_id in layer
            ]

            layer_results = await asyncio.gather(*tasks, return_exceptions=True)

            for node_id, result in zip(layer, layer_results):
                if isinstance(result, Exception):
                    nodes[node_id].status = NodeStatus.FAILED
                    nodes[node_id].error = result
                    # Skip dependent nodes
                    self._mark_dependents_skipped(node_id, nodes)
                else:
                    nodes[node_id].status = NodeStatus.COMPLETED
                    nodes[node_id].result = result
                    results[node_id] = result
                    context.node_results[node_id] = result

        return results

    async def _execute_node(
        self,
        node: WorkflowNode,
        context: WorkflowContext
    ) -> Any:
        """Execute single node với semaphore"""
        async with self.semaphore:
            node.status = NodeStatus.RUNNING
            return await node.execute(context)

    def _mark_dependents_skipped(
        self,
        failed_node_id: str,
        nodes: Dict[str, WorkflowNode]
    ) -> None:
        """Mark tất cả dependents của failed node là SKIPPED"""
        for node in nodes.values():
            if failed_node_id in node.dependencies:
                node.status = NodeStatus.SKIPPED
```

#### 5.2.3 Workflow Builder

```python
# app/workflow/builder.py
from typing import List

class ToolExecutionWorkflow:
    """Builder để tạo DAG từ tool calls"""

    def __init__(self):
        self.nodes: Dict[str, WorkflowNode] = {}
        self.node_counter = 0

    def add_tool_execution(
        self,
        tool_call: ToolCall,
        use_cache: bool = True
    ) -> str:
        """
        Thêm một tool execution vào workflow.
        Returns: ID của execution node.
        """
        prefix = f"tool_{self.node_counter}"
        self.node_counter += 1

        # 1. Parse node
        parse_id = f"{prefix}_parse"
        self.nodes[parse_id] = ParseNode(
            id=parse_id,
            tool_name=tool_call.name,
            raw_arguments=tool_call.arguments
        )

        # 2. Validate node (depends on parse)
        validate_id = f"{prefix}_validate"
        self.nodes[validate_id] = ValidateNode(
            id=validate_id,
            dependencies={parse_id},
            command=build_command(tool_call.name, tool_call.arguments)
        )

        # 3. Cache check node (parallel với validate nếu có cache)
        cache_check_id = f"{prefix}_cache_check"
        if use_cache:
            self.nodes[cache_check_id] = CacheCheckNode(
                id=cache_check_id,
                dependencies={parse_id},
                cache_key=self._make_cache_key(tool_call)
            )

        # 4. Execute node (depends on validate và cache miss)
        execute_id = f"{prefix}_execute"
        execute_deps = {validate_id}
        if use_cache:
            execute_deps.add(cache_check_id)

        self.nodes[execute_id] = ExecuteNode(
            id=execute_id,
            dependencies=execute_deps,
            command=build_command(tool_call.name, tool_call.arguments)
        )

        # 5. Cache store node (depends on execute)
        if use_cache:
            cache_store_id = f"{prefix}_cache_store"
            self.nodes[cache_store_id] = CacheNode(
                id=cache_store_id,
                dependencies={execute_id},
                cache_key=self._make_cache_key(tool_call),
                ttl=300
            )

        return execute_id

    def build(self) -> Dict[str, WorkflowNode]:
        return self.nodes

    def _make_cache_key(self, tool_call: ToolCall) -> str:
        import hashlib
        import json
        data = f"{tool_call.name}:{json.dumps(tool_call.arguments, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
```

#### 5.2.4 Tích Hợp vào FilesystemAgent

```python
# app/agent/filesystem_agent.py (modified)
from app.workflow.dag_executor import DAGExecutor, WorkflowContext
from app.workflow.builder import ToolExecutionWorkflow

class FilesystemAgent:
    def __init__(self, ..., dag_executor: Optional[DAGExecutor] = None):
        self.dag_executor = dag_executor or DAGExecutor(max_concurrency=5)

    async def _execute_tools_dag(
        self,
        tool_calls: List[ToolCall]
    ) -> List[ExecutionResult]:
        """Execute tools using DAG-based workflow"""

        # Build workflow
        workflow = ToolExecutionWorkflow()
        execution_ids = []
        for tool_call in tool_calls:
            exec_id = workflow.add_tool_execution(
                tool_call,
                use_cache=self.cache_manager is not None
            )
            execution_ids.append(exec_id)

        # Prepare context
        context = WorkflowContext()
        context.set("executor", self.executor)
        context.set("cache_manager", self.cache_manager)
        context.set("security_policy", self.security_policy)

        # Execute DAG
        results = await self.dag_executor.execute(
            workflow.build(),
            context
        )

        # Extract results in order
        return [
            results.get(exec_id)
            for exec_id in execution_ids
        ]
```

### 5.3 Lợi Ích của DAG

| Aspect | Trước (Linear) | Sau (DAG) |
|--------|----------------|-----------|
| **Parallelism** | Manual via orchestrator | Automatic từ dependency analysis |
| **Dependency Management** | Implicit | Explicit trong graph |
| **Error Handling** | Per-tool | Cascade skipping of dependents |
| **Observability** | Log-based | Graph visualization possible |
| **Extensibility** | Hard to add stages | Add new node types easily |
| **Testing** | Integration tests | Unit test mỗi node |

---

## 6. Repository Pattern

### 6.1 Vấn Đề Hiện Tại

#### Session Management (Anti-pattern)

```python
# app/api/routes/chat.py - HIỆN TẠI
_sessions: dict[str, list[dict]] = {}
_sessions_lock = asyncio.Lock()

# Direct access trong route handlers
async with _sessions_lock:
    history = _sessions.get(session_id, []).copy()
```

**Vấn đề:**
- Data access mixed với business logic
- Không có abstraction cho session lifecycle
- Khó migrate sang Redis/database
- Khó test

#### Cache Access

```python
# app/cache/cache_manager.py - HIỆN TẠI
class CacheManager:
    def __init__(self, cache_dir, ...):
        self.persistent_cache = PersistentCache(cache_dir, ...)
        self.content_cache = ContentCache(...)
        # Tight coupling với specific implementations
```

### 6.2 Repository Pattern Solution

#### 6.2.1 Base Repository Interface

```python
# app/repositories/base.py
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, List

T = TypeVar('T')

class Repository(ABC, Generic[T]):
    """Abstract base repository interface"""

    @abstractmethod
    async def get(self, id: str) -> Optional[T]:
        """Get entity by ID"""
        pass

    @abstractmethod
    async def get_all(self) -> List[T]:
        """Get all entities"""
        pass

    @abstractmethod
    async def add(self, entity: T) -> T:
        """Add new entity"""
        pass

    @abstractmethod
    async def update(self, id: str, entity: T) -> Optional[T]:
        """Update existing entity"""
        pass

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete entity by ID"""
        pass

    @abstractmethod
    async def exists(self, id: str) -> bool:
        """Check if entity exists"""
        pass
```

#### 6.2.2 Session Repository

```python
# app/repositories/session_repository.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import asyncio

@dataclass
class Session:
    """Session domain model"""
    id: str
    messages: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    max_messages: int = 50

    def add_message(self, role: str, content: str, **kwargs) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            **kwargs
        })
        self.last_accessed = datetime.utcnow()

        # Truncate if exceeds max
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_history(self) -> List[Dict]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages = []

class SessionRepository(Repository[Session]):
    """In-memory session repository"""

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: Dict[str, Session] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.ttl = timedelta(seconds=ttl_seconds)

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create lock cho session"""
        async with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def get(self, id: str) -> Optional[Session]:
        lock = await self._get_lock(id)
        async with lock:
            session = self._sessions.get(id)
            if session:
                session.last_accessed = datetime.utcnow()
            return session

    async def get_or_create(self, id: str) -> Session:
        """Get existing or create new session"""
        lock = await self._get_lock(id)
        async with lock:
            if id not in self._sessions:
                self._sessions[id] = Session(id=id)
            session = self._sessions[id]
            session.last_accessed = datetime.utcnow()
            return session

    async def get_all(self) -> List[Session]:
        async with self._global_lock:
            return list(self._sessions.values())

    async def add(self, entity: Session) -> Session:
        lock = await self._get_lock(entity.id)
        async with lock:
            self._sessions[entity.id] = entity
            return entity

    async def update(self, id: str, entity: Session) -> Optional[Session]:
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                self._sessions[id] = entity
                return entity
            return None

    async def delete(self, id: str) -> bool:
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                del self._sessions[id]
                return True
            return False

    async def exists(self, id: str) -> bool:
        async with self._global_lock:
            return id in self._sessions

    async def cleanup_expired(self) -> int:
        """Remove expired sessions"""
        now = datetime.utcnow()
        expired_ids = []

        async with self._global_lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed > self.ttl:
                    expired_ids.append(session_id)

        for session_id in expired_ids:
            await self.delete(session_id)

        return len(expired_ids)

# Redis implementation cho production
class RedisSessionRepository(Repository[Session]):
    """Redis-backed session repository"""

    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        import redis.asyncio as redis
        self.redis = redis.from_url(redis_url)
        self.ttl = ttl_seconds

    async def get(self, id: str) -> Optional[Session]:
        data = await self.redis.get(f"session:{id}")
        if data:
            return Session(**json.loads(data))
        return None

    async def add(self, entity: Session) -> Session:
        key = f"session:{entity.id}"
        await self.redis.setex(
            key,
            self.ttl,
            json.dumps(asdict(entity), default=str)
        )
        return entity

    # ... other methods
```

#### 6.2.3 Cache Repository

```python
# app/repositories/cache_repository.py
from abc import ABC, abstractmethod
from typing import Any, Optional

class CacheRepository(ABC):
    """Abstract interface cho cache operations"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set value with optional TTL"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete by key"""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        pass

    @abstractmethod
    def stats(self) -> dict:
        """Get cache statistics"""
        pass

class DiskCacheRepository(CacheRepository):
    """DiskCache-backed repository"""

    def __init__(self, cache_dir: str, size_limit: int):
        from diskcache import Cache
        self._cache = Cache(
            directory=cache_dir,
            size_limit=size_limit,
            eviction_policy="least-recently-used"
        )
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            value = self._cache.get(key)
            if value is not None:
                self._hits += 1
            else:
                self._misses += 1
            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        async with self._lock:
            if ttl:
                self._cache.set(key, value, expire=ttl)
            else:
                self._cache.set(key, value)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._cache.delete(key)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def exists(self, key: str) -> bool:
        async with self._lock:
            return key in self._cache

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
            "size": len(self._cache),
            "volume": self._cache.volume()
        }

class MemoryCacheRepository(CacheRepository):
    """In-memory cache cho testing"""

    def __init__(self, max_size: int = 1000):
        from collections import OrderedDict
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        async with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # LRU eviction
            self._cache[key] = value

    # ... other methods
```

#### 6.2.4 Tool Registry Repository

```python
# app/repositories/tool_registry.py
from dataclasses import dataclass
from typing import Dict, List, Callable, Optional

@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None

@dataclass
class ToolDefinition:
    """Complete tool definition"""
    name: str
    description: str
    parameters: List[ToolParameter]
    builder: Callable[[dict], list[str]]
    cacheable: bool = True
    cache_ttl: Optional[int] = None

    def to_openai_format(self) -> dict:
        """Convert to OpenAI function calling format"""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = {
                "type": param.type,
                "description": param.description
            }
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

class ToolRegistry:
    """Registry để manage tool definitions"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_all(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return list(self._tools.values())

    def to_openai_format(self) -> List[dict]:
        """Convert all tools to OpenAI format"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    def build_command(self, name: str, arguments: dict) -> list[str]:
        """Build command for a tool"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return tool.builder(arguments)

    def is_cacheable(self, name: str) -> bool:
        """Check if tool results should be cached"""
        tool = self.get(name)
        return tool.cacheable if tool else False

    def get_cache_ttl(self, name: str) -> Optional[int]:
        """Get cache TTL for tool"""
        tool = self.get(name)
        return tool.cache_ttl if tool else None

# Setup default tools
def create_default_registry() -> ToolRegistry:
    """Create registry với default tools"""
    registry = ToolRegistry()

    registry.register(ToolDefinition(
        name="grep",
        description="Search for a pattern in files",
        parameters=[
            ToolParameter("pattern", "string", "Regex pattern to search"),
            ToolParameter("path", "string", "File or directory to search"),
            ToolParameter("recursive", "boolean", "Search recursively", False, True),
            ToolParameter("ignore_case", "boolean", "Case insensitive", False, False),
        ],
        builder=lambda args: [
            "grep",
            "-r" if args.get("recursive", True) else "",
            "-i" if args.get("ignore_case", False) else "",
            args["pattern"],
            args["path"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    registry.register(ToolDefinition(
        name="cat",
        description="Display file contents",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
        ],
        builder=lambda args: ["cat", args["path"]],
        cacheable=True,
        cache_ttl=0  # Invalidate on file change only
    ))

    # ... register other tools

    return registry
```

### 6.3 Tích Hợp Repository vào Application

```python
# app/dependencies.py
from functools import lru_cache
from app.repositories.session_repository import SessionRepository
from app.repositories.cache_repository import DiskCacheRepository
from app.repositories.tool_registry import ToolRegistry, create_default_registry

@lru_cache()
def get_session_repository() -> SessionRepository:
    return SessionRepository(ttl_seconds=3600)

@lru_cache()
def get_cache_repository() -> CacheRepository:
    settings = get_settings()
    return DiskCacheRepository(
        cache_dir=settings.cache_directory,
        size_limit=settings.cache_size_limit
    )

@lru_cache()
def get_tool_registry() -> ToolRegistry:
    return create_default_registry()

# app/api/routes/chat.py (refactored)
from app.dependencies import get_session_repository

@router.post("/chat")
async def chat(
    request: ChatRequest,
    session_repo: SessionRepository = Depends(get_session_repository),
    agent: FilesystemAgent = Depends(get_agent),
):
    session_id = request.session_id or str(uuid.uuid4())

    # Use repository instead of direct dict access
    session = await session_repo.get_or_create(session_id)

    response = await agent.chat(
        request.message,
        session.get_history()
    )

    session.add_message("user", request.message)
    session.add_message("assistant", response.message)
    await session_repo.update(session_id, session)

    return ChatResponse(
        response=response.message,
        session_id=session_id,
        ...
    )
```

---

## 7. Factory Pattern

### 7.1 Vấn Đề Hiện Tại

```python
# app/agent/filesystem_agent.py - HIỆN TẠI
def create_agent(
    api_key: str,
    endpoint: str,
    deployment_name: str,
    api_version: str,
    data_root: Path,
    sandbox_enabled: bool = True,
    parallel_enabled: bool = True,
    max_concurrent_tools: int = 5,
    use_legacy_cache: bool = False,
    legacy_cache_ttl: int = 300,
    legacy_cache_max_size: int = 100,
    use_new_cache: bool = False,
    cache_directory: str = "tmp/cache",
    cache_size_limit: int = 500 * 1024 * 1024,
    cache_content_ttl: int = 0,
    cache_search_ttl: int = 300,
) -> FilesystemAgent:
    # 30+ lines of initialization code
    ...
```

**Vấn đề:**
- 15+ parameters
- Complex initialization logic
- Hard to maintain
- Difficult to test

### 7.2 Factory Pattern Solution

#### 7.2.1 Configuration Objects

```python
# app/config/agent_config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class OpenAIConfig:
    """Azure OpenAI configuration"""
    api_key: str
    endpoint: str
    deployment_name: str
    api_version: str = "2024-02-15-preview"

@dataclass
class SandboxConfig:
    """Sandbox execution configuration"""
    enabled: bool = True
    root_path: Path = field(default_factory=lambda: Path("./data"))
    timeout: int = 30
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_output_size: int = 1024 * 1024  # 1MB

@dataclass
class CacheConfig:
    """Cache system configuration"""
    enabled: bool = True
    use_new_cache: bool = True
    directory: str = "tmp/cache"
    size_limit: int = 500 * 1024 * 1024  # 500MB
    content_ttl: int = 0
    search_ttl: int = 300

@dataclass
class OrchestratorConfig:
    """Tool orchestration configuration"""
    parallel_enabled: bool = True
    max_concurrent_tools: int = 5

@dataclass
class AgentConfig:
    """Complete agent configuration"""
    openai: OpenAIConfig
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    max_tool_iterations: int = 10

    @classmethod
    def from_settings(cls, settings: "Settings") -> "AgentConfig":
        """Create config from application settings"""
        return cls(
            openai=OpenAIConfig(
                api_key=settings.azure_openai_api_key,
                endpoint=settings.azure_openai_endpoint,
                deployment_name=settings.azure_openai_deployment_name,
                api_version=settings.azure_openai_api_version,
            ),
            sandbox=SandboxConfig(
                enabled=settings.sandbox_enabled,
                root_path=Path(settings.data_root_path),
                timeout=settings.command_timeout,
            ),
            cache=CacheConfig(
                enabled=settings.cache_enabled,
                use_new_cache=settings.use_new_cache,
                directory=settings.cache_directory,
                size_limit=settings.cache_size_limit,
            ),
            orchestrator=OrchestratorConfig(
                parallel_enabled=settings.parallel_execution,
                max_concurrent_tools=settings.max_concurrent_tools,
            ),
        )
```

#### 7.2.2 Component Factories

```python
# app/factories/component_factory.py
from abc import ABC, abstractmethod
from typing import Optional

class ComponentFactory(ABC):
    """Abstract factory cho agent components"""

    @abstractmethod
    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        pass

    @abstractmethod
    def create_executor(self, config: SandboxConfig) -> SandboxExecutor:
        pass

    @abstractmethod
    def create_cache_manager(self, config: CacheConfig) -> Optional[CacheManager]:
        pass

    @abstractmethod
    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: SandboxExecutor
    ) -> ParallelToolOrchestrator:
        pass

class DefaultComponentFactory(ComponentFactory):
    """Default factory implementation"""

    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        return AsyncAzureOpenAI(
            api_key=config.api_key,
            azure_endpoint=config.endpoint,
            api_version=config.api_version,
        )

    def create_executor(self, config: SandboxConfig) -> SandboxExecutor:
        return SandboxExecutor(
            root_path=config.root_path,
            timeout=config.timeout,
            max_file_size=config.max_file_size,
            max_output_size=config.max_output_size,
            sandbox_enabled=config.enabled,
        )

    def create_cache_manager(self, config: CacheConfig) -> Optional[CacheManager]:
        if not config.enabled:
            return None

        if config.use_new_cache:
            return CacheManager(
                cache_dir=config.directory,
                size_limit=config.size_limit,
                content_ttl=config.content_ttl,
                search_ttl=config.search_ttl,
            )
        return None

    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: SandboxExecutor
    ) -> ParallelToolOrchestrator:
        return ParallelToolOrchestrator(
            executor=executor,
            max_concurrent=config.max_concurrent_tools,
            parallel_enabled=config.parallel_enabled,
        )

class TestComponentFactory(ComponentFactory):
    """Factory cho testing với mocked components"""

    def __init__(self, mock_client=None, mock_executor=None):
        self.mock_client = mock_client
        self.mock_executor = mock_executor

    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        return self.mock_client or MockAzureOpenAI()

    def create_executor(self, config: SandboxConfig) -> SandboxExecutor:
        return self.mock_executor or MockSandboxExecutor()

    def create_cache_manager(self, config: CacheConfig) -> Optional[CacheManager]:
        return MockCacheManager() if config.enabled else None

    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: SandboxExecutor
    ) -> ParallelToolOrchestrator:
        return ParallelToolOrchestrator(
            executor=executor,
            max_concurrent=config.max_concurrent_tools,
        )
```

#### 7.2.3 Agent Factory

```python
# app/factories/agent_factory.py
from typing import Optional

class AgentFactory:
    """Factory để tạo FilesystemAgent"""

    def __init__(
        self,
        component_factory: Optional[ComponentFactory] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.component_factory = component_factory or DefaultComponentFactory()
        self.tool_registry = tool_registry or create_default_registry()

    def create(self, config: AgentConfig) -> FilesystemAgent:
        """Create fully configured agent"""

        # Create components
        client = self.component_factory.create_client(config.openai)
        executor = self.component_factory.create_executor(config.sandbox)
        cache_manager = self.component_factory.create_cache_manager(config.cache)
        orchestrator = self.component_factory.create_orchestrator(
            config.orchestrator,
            executor
        )

        # Create agent
        return FilesystemAgent(
            client=client,
            deployment_name=config.openai.deployment_name,
            executor=executor,
            orchestrator=orchestrator,
            cache_manager=cache_manager,
            tool_registry=self.tool_registry,
            max_iterations=config.max_tool_iterations,
        )

    def create_from_settings(self, settings: "Settings") -> FilesystemAgent:
        """Create agent from application settings"""
        config = AgentConfig.from_settings(settings)
        return self.create(config)

# Singleton factory instance
_agent_factory: Optional[AgentFactory] = None

def get_agent_factory() -> AgentFactory:
    """Get or create agent factory singleton"""
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()
    return _agent_factory
```

#### 7.2.4 Sử Dụng Factory

```python
# app/dependencies.py
from app.factories.agent_factory import AgentFactory, get_agent_factory

def get_agent(
    settings: Settings = Depends(get_settings),
    factory: AgentFactory = Depends(get_agent_factory),
) -> FilesystemAgent:
    """Dependency injection cho agent"""
    return factory.create_from_settings(settings)

# Testing
def test_agent_with_mock():
    mock_factory = TestComponentFactory(
        mock_client=MockAzureOpenAI(),
        mock_executor=MockSandboxExecutor(),
    )

    factory = AgentFactory(component_factory=mock_factory)
    agent = factory.create(test_config)

    # Test với mocked dependencies
    response = await agent.chat("test message")
```

---

## 8. Các Patterns Bổ Sung

### 8.1 Strategy Pattern cho Invalidation

```python
# app/cache/strategies/invalidation.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class InvalidationContext:
    """Context cho invalidation checks"""
    key: str
    path: Optional[Path] = None
    ttl: Optional[int] = None
    created_at: Optional[datetime] = None

class InvalidationStrategy(ABC):
    """Abstract strategy cho cache invalidation"""

    @abstractmethod
    async def is_stale(self, context: InvalidationContext) -> bool:
        """Check if cache entry is stale"""
        pass

class FileStateInvalidation(InvalidationStrategy):
    """Invalidate khi file thay đổi"""

    def __init__(self, state_tracker: FileStateTracker):
        self.tracker = state_tracker

    async def is_stale(self, context: InvalidationContext) -> bool:
        if context.path:
            return await self.tracker.is_stale(context.path)
        return False

class TTLInvalidation(InvalidationStrategy):
    """Invalidate sau TTL"""

    async def is_stale(self, context: InvalidationContext) -> bool:
        if context.ttl and context.created_at:
            elapsed = (datetime.utcnow() - context.created_at).total_seconds()
            return elapsed > context.ttl
        return False

class CompositeInvalidation(InvalidationStrategy):
    """Combine multiple strategies (OR logic - stale if ANY says stale)"""

    def __init__(self, strategies: List[InvalidationStrategy]):
        self.strategies = strategies

    async def is_stale(self, context: InvalidationContext) -> bool:
        for strategy in self.strategies:
            if await strategy.is_stale(context):
                return True
        return False

# Usage
content_strategy = CompositeInvalidation([
    FileStateInvalidation(state_tracker),
    TTLInvalidation(),
])
```

### 8.2 Chain of Responsibility cho Tool Handlers

```python
# app/agent/handlers/tool_handlers.py
from abc import ABC, abstractmethod
from typing import Optional

class ToolHandler(ABC):
    """Abstract tool handler"""

    def __init__(self, next_handler: Optional["ToolHandler"] = None):
        self.next = next_handler

    async def handle(self, tool_call: ToolCall) -> ExecutionResult:
        """Handle or pass to next handler"""
        if self.can_handle(tool_call):
            return await self._do_handle(tool_call)
        elif self.next:
            return await self.next.handle(tool_call)
        else:
            raise ValueError(f"No handler for tool: {tool_call.name}")

    @abstractmethod
    def can_handle(self, tool_call: ToolCall) -> bool:
        """Check if this handler can process the tool call"""
        pass

    @abstractmethod
    async def _do_handle(self, tool_call: ToolCall) -> ExecutionResult:
        """Actually handle the tool call"""
        pass

class CachedReadHandler(ToolHandler):
    """Handler cho cached read operations"""

    READ_TOOLS = {"cat", "head", "tail"}

    def __init__(
        self,
        content_cache: ContentCache,
        executor: SandboxExecutor,
        next_handler: Optional[ToolHandler] = None
    ):
        super().__init__(next_handler)
        self.cache = content_cache
        self.executor = executor

    def can_handle(self, tool_call: ToolCall) -> bool:
        return tool_call.name in self.READ_TOOLS

    async def _do_handle(self, tool_call: ToolCall) -> ExecutionResult:
        # Try cache first
        path = tool_call.arguments.get("path")

        async def loader():
            command = build_command(tool_call.name, tool_call.arguments)
            return await self.executor.execute(command)

        return await self.cache.get_content(path, loader)

class CachedSearchHandler(ToolHandler):
    """Handler cho cached search operations"""

    SEARCH_TOOLS = {"grep", "find"}

    def __init__(
        self,
        search_cache: SearchCache,
        executor: SandboxExecutor,
        next_handler: Optional[ToolHandler] = None
    ):
        super().__init__(next_handler)
        self.cache = search_cache
        self.executor = executor

    def can_handle(self, tool_call: ToolCall) -> bool:
        return tool_call.name in self.SEARCH_TOOLS

    async def _do_handle(self, tool_call: ToolCall) -> ExecutionResult:
        # Cached search logic
        ...

class DefaultHandler(ToolHandler):
    """Default handler - execute directly"""

    def __init__(self, executor: SandboxExecutor):
        super().__init__(None)  # No next handler
        self.executor = executor

    def can_handle(self, tool_call: ToolCall) -> bool:
        return True  # Handles everything

    async def _do_handle(self, tool_call: ToolCall) -> ExecutionResult:
        command = build_command(tool_call.name, tool_call.arguments)
        return await self.executor.execute(command)

# Build chain
def create_handler_chain(
    content_cache: ContentCache,
    search_cache: SearchCache,
    executor: SandboxExecutor,
) -> ToolHandler:
    """Create chain of responsibility"""
    default = DefaultHandler(executor)
    search = CachedSearchHandler(search_cache, executor, default)
    read = CachedReadHandler(content_cache, executor, search)
    return read
```

### 8.3 Observer Pattern cho Cache Events

```python
# app/cache/observers/cache_observer.py
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Any, List

class CacheEventType(Enum):
    HIT = "hit"
    MISS = "miss"
    SET = "set"
    DELETE = "delete"
    INVALIDATE = "invalidate"
    EVICT = "evict"

@dataclass
class CacheEvent:
    """Cache event data"""
    event_type: CacheEventType
    key: str
    value: Optional[Any] = None
    metadata: dict = field(default_factory=dict)

class CacheObserver(ABC):
    """Abstract cache event observer"""

    @abstractmethod
    async def on_event(self, event: CacheEvent) -> None:
        """Handle cache event"""
        pass

class MetricsObserver(CacheObserver):
    """Record cache metrics"""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.evictions = 0

    async def on_event(self, event: CacheEvent) -> None:
        if event.event_type == CacheEventType.HIT:
            self.hits += 1
        elif event.event_type == CacheEventType.MISS:
            self.misses += 1
        elif event.event_type == CacheEventType.SET:
            self.sets += 1
        elif event.event_type == CacheEventType.EVICT:
            self.evictions += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0

class LoggingObserver(CacheObserver):
    """Log cache events"""

    def __init__(self, logger):
        self.logger = logger

    async def on_event(self, event: CacheEvent) -> None:
        self.logger.debug(
            f"Cache {event.event_type.value}: {event.key}",
            extra=event.metadata
        )

class CacheEventManager:
    """Manage cache observers"""

    def __init__(self):
        self.observers: List[CacheObserver] = []

    def subscribe(self, observer: CacheObserver) -> None:
        self.observers.append(observer)

    def unsubscribe(self, observer: CacheObserver) -> None:
        self.observers.remove(observer)

    async def notify(self, event: CacheEvent) -> None:
        for observer in self.observers:
            await observer.on_event(event)
```

### 8.4 Exception Hierarchy

```python
# app/exceptions.py
from typing import Optional

class FilesystemAgentException(Exception):
    """Base exception cho tất cả agent errors"""
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

# Global exception handler
from fastapi import Request
from fastapi.responses import JSONResponse

async def agent_exception_handler(
    request: Request,
    exc: FilesystemAgentException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        }
    )

# Register in FastAPI
app.add_exception_handler(FilesystemAgentException, agent_exception_handler)
```

---

## 9. Lộ Trình Triển Khai

### Phase 1: Foundation (Tuần 1-2)

**Priority: HIGH**

| Task | Files | Effort |
|------|-------|--------|
| Tạo Exception Hierarchy | `app/exceptions.py` | 4h |
| Tạo Configuration Objects | `app/config/agent_config.py` | 6h |
| Implement Repository Base | `app/repositories/base.py` | 4h |
| Implement SessionRepository | `app/repositories/session_repository.py` | 8h |
| Refactor chat.py sử dụng repository | `app/api/routes/chat.py` | 6h |

**Deliverables:**
- Centralized exception handling
- Type-safe configuration
- Session management với proper abstraction

### Phase 2: Factory & Registry (Tuần 3-4)

**Priority: MEDIUM-HIGH**

| Task | Files | Effort |
|------|-------|--------|
| Implement ToolRegistry | `app/repositories/tool_registry.py` | 8h |
| Implement ComponentFactory | `app/factories/component_factory.py` | 6h |
| Implement AgentFactory | `app/factories/agent_factory.py` | 8h |
| Refactor FilesystemAgent | `app/agent/filesystem_agent.py` | 12h |
| Update dependencies | `app/dependencies.py` | 4h |

**Deliverables:**
- Clean agent creation flow
- Testable components
- Self-documenting tool definitions

### Phase 3: Cache Improvements (Tuần 5-6)

**Priority: MEDIUM**

| Task | Files | Effort |
|------|-------|--------|
| Implement CacheRepository | `app/repositories/cache_repository.py` | 8h |
| Implement InvalidationStrategies | `app/cache/strategies/invalidation.py` | 8h |
| Implement CacheObservers | `app/cache/observers/cache_observer.py` | 6h |
| Refactor CacheManager | `app/cache/cache_manager.py` | 10h |
| Add metrics collection | `app/cache/metrics.py` | 4h |

**Deliverables:**
- Swappable cache backends
- Configurable invalidation policies
- Observable cache behavior

### Phase 4: DAG & Handler Chain (Tuần 7-8)

**Priority: MEDIUM**

| Task | Files | Effort |
|------|-------|--------|
| Implement WorkflowNodes | `app/workflow/nodes.py` | 10h |
| Implement DAGExecutor | `app/workflow/dag_executor.py` | 12h |
| Implement WorkflowBuilder | `app/workflow/builder.py` | 8h |
| Implement ToolHandlers (CoR) | `app/agent/handlers/tool_handlers.py` | 10h |
| Integration testing | `tests/test_workflow.py` | 8h |

**Deliverables:**
- DAG-based tool execution
- Automatic parallel execution
- Chain of responsibility cho tool handling

### Phase 5: Testing & Documentation (Tuần 9-10)

**Priority: HIGH**

| Task | Files | Effort |
|------|-------|--------|
| Unit tests cho repositories | `tests/test_repositories.py` | 12h |
| Unit tests cho factories | `tests/test_factories.py` | 8h |
| Integration tests | `tests/test_integration_patterns.py` | 12h |
| Performance benchmarks | `benchmarks/benchmark_patterns.py` | 8h |
| Documentation updates | `docs/` | 8h |

**Deliverables:**
- Comprehensive test coverage (>80%)
- Performance validation
- Updated documentation

---

## 10. Kết Luận

### 10.1 Tóm Tắt Đề Xuất

| Pattern | Vị Trí Áp Dụng | Lợi Ích | Priority |
|---------|----------------|---------|----------|
| **DAG** | Tool Execution | Automatic parallelism, clear dependencies | Medium |
| **Repository** | Sessions, Cache, Tools | Abstraction, testability, flexibility | High |
| **Factory** | Agent Creation | Clean construction, testability | High |
| **Strategy** | Cache Invalidation | Configurable policies | Medium |
| **Chain of Responsibility** | Tool Handlers | Extensible, maintainable | Medium |
| **Observer** | Cache Events | Observability, metrics | Low |
| **Exception Hierarchy** | Error Handling | Consistent API errors | High |

### 10.2 Estimated Total Effort

| Phase | Duration | Effort |
|-------|----------|--------|
| Phase 1: Foundation | 2 tuần | 28h |
| Phase 2: Factory & Registry | 2 tuần | 38h |
| Phase 3: Cache Improvements | 2 tuần | 36h |
| Phase 4: DAG & Handlers | 2 tuần | 48h |
| Phase 5: Testing & Docs | 2 tuần | 48h |
| **Total** | **10 tuần** | **~200h** |

### 10.3 Metrics Mong Đợi

| Metric | Hiện Tại | Sau Cải Tiến |
|--------|----------|--------------|
| Test Coverage | ~60% | >80% |
| Code Coupling | High | Low |
| Maintainability | Medium | High |
| Testability | Medium | High |
| Extensibility | Low | High |
| Documentation | Basic | Comprehensive |

### 10.4 Recommendations

1. **Bắt đầu với Phase 1** - Foundation patterns (Exception, Config, Repository) mang lại giá trị ngay lập tức
2. **Factory Pattern** nên được implement trước khi DAG vì nó simplify testing
3. **Repository Pattern** cho sessions là critical cho production readiness
4. **DAG** có complexity cao nhưng long-term benefits cho maintainability
5. **Testing** nên được thực hiện song song với mỗi phase

---

## Appendix: Dependency Graph Sau Cải Tiến

```
┌─────────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                           │
│  chat.py, stream.py, documents.py                                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Dependencies Layer                              │
│  get_agent(), get_session_repo(), get_cache_repo()                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  AgentFactory   │   │ SessionRepository│   │ CacheRepository │
│ (Component      │   │ (Memory/Redis)   │   │ (Disk/Memory)   │
│  Factory)       │   │                  │   │                 │
└────────┬────────┘   └──────────────────┘   └────────┬────────┘
         │                                            │
         ▼                                            ▼
┌─────────────────┐                        ┌─────────────────┐
│FilesystemAgent  │◄───────────────────────│  CacheManager   │
│ (ToolRegistry,  │                        │ (ContentCache,  │
│  HandlerChain,  │                        │  SearchCache,   │
│  DAGExecutor)   │                        │  Observer)      │
└────────┬────────┘                        └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Tool Execution Layer                             │
│  ToolHandler Chain → DAGExecutor → SandboxExecutor                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

*Báo cáo này được tạo bởi Claude AI dựa trên phân tích code của dự án Filesystem Agent Showcase.*
