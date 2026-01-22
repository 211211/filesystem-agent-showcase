# Implementation Roadmap: Design Patterns Step-by-Step

> **Mục tiêu**: Triển khai từng design pattern một cách tuần tự, đảm bảo code luôn chạy được sau mỗi bước.
> **Tổng thời gian ước tính**: 10 tuần (~200 giờ)

---

## Mục Lục

- [Phase 1: Foundation](#phase-1-foundation-tuần-1-2)
- [Phase 2: Factory & Registry](#phase-2-factory--registry-tuần-3-4)
- [Phase 3: Cache Improvements](#phase-3-cache-improvements-tuần-5-6)
- [Phase 4: DAG & Handler Chain](#phase-4-dag--handler-chain-tuần-7-8)
- [Phase 5: Testing & Documentation](#phase-5-testing--documentation-tuần-9-10)

---

## Phase 1: Foundation (Tuần 1-2)

**Mục tiêu**: Xây dựng nền tảng với Exception Hierarchy, Configuration Objects, và Repository Pattern cho Sessions.

### Step 1.1: Exception Hierarchy (4h)

**Tạo file**: `app/exceptions.py`

```bash
# Tạo file mới
touch app/exceptions.py
```

**Tasks**:
1. [ ] Tạo base exception `FilesystemAgentException`
2. [ ] Tạo security exceptions (`PathTraversalException`, `CommandNotAllowedException`)
3. [ ] Tạo execution exceptions (`TimeoutException`, `OutputSizeException`)
4. [ ] Tạo validation và session exceptions
5. [ ] Tạo global exception handler cho FastAPI

**Code Template**:

```python
# app/exceptions.py
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse

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

class CacheException(FilesystemAgentException):
    """Cache-related errors"""
    status_code = 500
    error_code = "CACHE_ERROR"

# Global exception handler
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
```

**Integration**:

```python
# app/main.py - thêm vào sau khi tạo app
from app.exceptions import FilesystemAgentException, agent_exception_handler

app.add_exception_handler(FilesystemAgentException, agent_exception_handler)
```

**Refactor existing code**:

```python
# app/sandbox/executor.py - thay đổi
# Trước:
raise ValueError(f"Command not allowed: {cmd_name}")

# Sau:
from app.exceptions import CommandNotAllowedException
raise CommandNotAllowedException(f"Command not allowed: {cmd_name}")
```

**Test**:
```bash
poetry run pytest tests/test_exceptions.py -v
```

---

### Step 1.2: Configuration Objects (6h)

**Tạo thư mục và files**:
```bash
mkdir -p app/config
touch app/config/__init__.py
touch app/config/agent_config.py
```

**Tasks**:
1. [ ] Tạo `OpenAIConfig` dataclass
2. [ ] Tạo `SandboxConfig` dataclass
3. [ ] Tạo `CacheConfig` dataclass
4. [ ] Tạo `OrchestratorConfig` dataclass
5. [ ] Tạo `AgentConfig` với `from_settings()` method
6. [ ] Update `app/config.py` để export configs

**Code Template**:

```python
# app/config/agent_config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

@dataclass(frozen=True)
class OpenAIConfig:
    """Azure OpenAI configuration"""
    api_key: str
    endpoint: str
    deployment_name: str
    api_version: str = "2024-02-15-preview"

@dataclass(frozen=True)
class SandboxConfig:
    """Sandbox execution configuration"""
    enabled: bool = True
    root_path: Path = field(default_factory=lambda: Path("./data"))
    timeout: int = 30
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    max_output_size: int = 1024 * 1024  # 1MB

@dataclass(frozen=True)
class CacheConfig:
    """Cache system configuration"""
    enabled: bool = True
    use_new_cache: bool = True
    directory: str = "tmp/cache"
    size_limit: int = 500 * 1024 * 1024  # 500MB
    content_ttl: int = 0
    search_ttl: int = 300

@dataclass(frozen=True)
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
                max_file_size=settings.max_file_size,
                max_output_size=settings.max_output_size,
            ),
            cache=CacheConfig(
                enabled=settings.cache_enabled,
                use_new_cache=settings.use_new_cache,
                directory=settings.cache_directory,
                size_limit=settings.cache_size_limit,
                content_ttl=settings.cache_content_ttl,
                search_ttl=settings.cache_search_ttl,
            ),
            orchestrator=OrchestratorConfig(
                parallel_enabled=settings.parallel_execution,
                max_concurrent_tools=settings.max_concurrent_tools,
            ),
        )
```

```python
# app/config/__init__.py
from app.config.agent_config import (
    OpenAIConfig,
    SandboxConfig,
    CacheConfig,
    OrchestratorConfig,
    AgentConfig,
)

__all__ = [
    "OpenAIConfig",
    "SandboxConfig",
    "CacheConfig",
    "OrchestratorConfig",
    "AgentConfig",
]
```

**Test**:
```bash
poetry run pytest tests/test_config.py -v
```

---

### Step 1.3: Repository Base Interface (4h)

**Tạo thư mục và files**:
```bash
mkdir -p app/repositories
touch app/repositories/__init__.py
touch app/repositories/base.py
```

**Tasks**:
1. [ ] Tạo generic `Repository[T]` ABC
2. [ ] Define CRUD methods
3. [ ] Add type hints

**Code Template**:

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

---

### Step 1.4: Session Repository (8h)

**Tạo file**: `app/repositories/session_repository.py`

**Tasks**:
1. [ ] Tạo `Session` domain model (dataclass)
2. [ ] Implement `SessionRepository` (in-memory)
3. [ ] Add per-session locking
4. [ ] Add TTL-based cleanup
5. [ ] Add `get_or_create()` method

**Code Template**:

```python
# app/repositories/session_repository.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import asyncio

from app.repositories.base import Repository

@dataclass
class Session:
    """Session domain model"""
    id: str
    messages: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    max_messages: int = 50

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add message to session history"""
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
        """Get copy of message history"""
        return self.messages.copy()

    def clear(self) -> None:
        """Clear all messages"""
        self.messages = []
        self.last_accessed = datetime.utcnow()

class SessionRepository(Repository[Session]):
    """In-memory session repository with per-session locking"""

    def __init__(self, ttl_seconds: int = 3600, max_messages: int = 50):
        self._sessions: Dict[str, Session] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_messages = max_messages

    async def _get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create lock for session"""
        async with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

    async def get(self, id: str) -> Optional[Session]:
        """Get session by ID"""
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
                self._sessions[id] = Session(
                    id=id,
                    max_messages=self.max_messages
                )
            session = self._sessions[id]
            session.last_accessed = datetime.utcnow()
            return session

    async def get_all(self) -> List[Session]:
        """Get all sessions"""
        async with self._global_lock:
            return list(self._sessions.values())

    async def add(self, entity: Session) -> Session:
        """Add new session"""
        lock = await self._get_lock(entity.id)
        async with lock:
            self._sessions[entity.id] = entity
            return entity

    async def update(self, id: str, entity: Session) -> Optional[Session]:
        """Update existing session"""
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                self._sessions[id] = entity
                return entity
            return None

    async def delete(self, id: str) -> bool:
        """Delete session by ID"""
        lock = await self._get_lock(id)
        async with lock:
            if id in self._sessions:
                del self._sessions[id]
                # Also remove the lock
                async with self._global_lock:
                    self._locks.pop(id, None)
                return True
            return False

    async def exists(self, id: str) -> bool:
        """Check if session exists"""
        async with self._global_lock:
            return id in self._sessions

    async def cleanup_expired(self) -> int:
        """Remove expired sessions, returns count of removed sessions"""
        now = datetime.utcnow()
        expired_ids = []

        async with self._global_lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed > self.ttl:
                    expired_ids.append(session_id)

        for session_id in expired_ids:
            await self.delete(session_id)

        return len(expired_ids)

    async def count(self) -> int:
        """Get total session count"""
        async with self._global_lock:
            return len(self._sessions)
```

```python
# app/repositories/__init__.py
from app.repositories.base import Repository
from app.repositories.session_repository import Session, SessionRepository

__all__ = [
    "Repository",
    "Session",
    "SessionRepository",
]
```

**Test**:
```bash
# Tạo test file
touch tests/test_session_repository.py
poetry run pytest tests/test_session_repository.py -v
```

---

### Step 1.5: Refactor chat.py to use Repository (6h)

**Tasks**:
1. [ ] Tạo `app/dependencies.py` cho dependency injection
2. [ ] Thêm `get_session_repository()` dependency
3. [ ] Refactor `chat.py` để sử dụng `SessionRepository`
4. [ ] Remove global `_sessions` dict
5. [ ] Update tests

**Code Changes**:

```python
# app/dependencies.py
from functools import lru_cache
from app.config import Settings
from app.repositories.session_repository import SessionRepository

# Settings dependency
@lru_cache()
def get_settings() -> Settings:
    return Settings()

# Session repository singleton
_session_repository: SessionRepository | None = None

def get_session_repository() -> SessionRepository:
    """Get or create session repository singleton"""
    global _session_repository
    if _session_repository is None:
        settings = get_settings()
        _session_repository = SessionRepository(
            ttl_seconds=3600,
            max_messages=50
        )
    return _session_repository
```

```python
# app/api/routes/chat.py - REFACTORED
from fastapi import APIRouter, Depends, HTTPException
from uuid import uuid4

from app.dependencies import get_settings, get_session_repository
from app.repositories.session_repository import SessionRepository
# ... other imports

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session_repo: SessionRepository = Depends(get_session_repository),
    # agent: FilesystemAgent = Depends(get_agent),  # Will add in Phase 2
):
    """Send a message and get a response"""
    session_id = request.session_id or str(uuid4())

    # Get or create session using repository
    session = await session_repo.get_or_create(session_id)

    # Get history from session
    history = session.get_history()

    # Call agent (keep existing logic for now)
    # response = await agent.chat(request.message, history)

    # Update session with new messages
    session.add_message("user", request.message)
    # session.add_message("assistant", response.message)
    await session_repo.update(session_id, session)

    return ChatResponse(
        # response=response.message,
        session_id=session_id,
        # ...
    )

@router.delete("/sessions/{session_id}")
async def clear_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository),
):
    """Clear session history"""
    session = await session_repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.clear()
    await session_repo.update(session_id, session)
    return {"message": "Session cleared"}

@router.get("/sessions/{session_id}/history")
async def get_history(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository),
):
    """Get session history"""
    session = await session_repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"session_id": session_id, "history": session.get_history()}
```

**Test**:
```bash
poetry run pytest tests/test_chat.py -v
poetry run pytest tests/test_session_repository.py -v
```

---

### Phase 1 Checklist

- [ ] Step 1.1: Exception Hierarchy implemented
- [ ] Step 1.2: Configuration Objects created
- [ ] Step 1.3: Repository Base Interface defined
- [ ] Step 1.4: Session Repository implemented
- [ ] Step 1.5: chat.py refactored to use Repository
- [ ] All tests passing
- [ ] Code reviewed

---

## Phase 2: Factory & Registry (Tuần 3-4)

**Mục tiêu**: Implement Factory Pattern cho agent creation và Tool Registry.

### Step 2.1: Tool Registry (8h)

**Tạo file**: `app/repositories/tool_registry.py`

**Tasks**:
1. [ ] Tạo `ToolParameter` dataclass
2. [ ] Tạo `ToolDefinition` dataclass với `to_openai_format()`
3. [ ] Implement `ToolRegistry` class
4. [ ] Tạo `create_default_registry()` với tất cả tools
5. [ ] Add tests

**Code Template**:

```python
# app/repositories/tool_registry.py
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional, Any

@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[str]] = None

@dataclass
class ToolDefinition:
    """Complete tool definition"""
    name: str
    description: str
    parameters: List[ToolParameter]
    builder: Callable[[dict], List[str]]
    cacheable: bool = True
    cache_ttl: Optional[int] = None

    def to_openai_format(self) -> dict:
        """Convert to OpenAI function calling format"""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop

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
    """Registry to manage tool definitions"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name"""
        return self._tools.get(name)

    def list_all(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        """List all tool names"""
        return list(self._tools.keys())

    def to_openai_format(self) -> List[dict]:
        """Convert all tools to OpenAI format"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    def build_command(self, name: str, arguments: dict) -> List[str]:
        """Build command for a tool"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        # Filter empty strings from command
        cmd = tool.builder(arguments)
        return [arg for arg in cmd if arg]

    def is_cacheable(self, name: str) -> bool:
        """Check if tool results should be cached"""
        tool = self.get(name)
        return tool.cacheable if tool else False

    def get_cache_ttl(self, name: str) -> Optional[int]:
        """Get cache TTL for tool"""
        tool = self.get(name)
        return tool.cache_ttl if tool else None

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_default_registry() -> ToolRegistry:
    """Create registry with default bash tools"""
    registry = ToolRegistry()

    # grep tool
    registry.register(ToolDefinition(
        name="grep",
        description="Search for a pattern in files using grep",
        parameters=[
            ToolParameter("pattern", "string", "The regex pattern to search for"),
            ToolParameter("path", "string", "File or directory path to search"),
            ToolParameter("recursive", "boolean", "Search recursively in directories", False, True),
            ToolParameter("ignore_case", "boolean", "Case insensitive search", False, False),
            ToolParameter("line_number", "boolean", "Show line numbers", False, True),
        ],
        builder=lambda args: [
            "grep",
            "-r" if args.get("recursive", True) else "",
            "-i" if args.get("ignore_case", False) else "",
            "-n" if args.get("line_number", True) else "",
            args["pattern"],
            args["path"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    # find tool
    registry.register(ToolDefinition(
        name="find",
        description="Find files by name pattern",
        parameters=[
            ToolParameter("path", "string", "Directory to search in"),
            ToolParameter("name", "string", "File name pattern (supports wildcards)"),
            ToolParameter("type", "string", "File type: f (file), d (directory)", False, "f"),
        ],
        builder=lambda args: [
            "find",
            args["path"],
            "-type", args.get("type", "f"),
            "-name", args["name"]
        ],
        cacheable=True,
        cache_ttl=300
    ))

    # cat tool
    registry.register(ToolDefinition(
        name="cat",
        description="Display entire file contents",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
        ],
        builder=lambda args: ["cat", args["path"]],
        cacheable=True,
        cache_ttl=0  # Invalidate on file change only
    ))

    # head tool
    registry.register(ToolDefinition(
        name="head",
        description="Display first N lines of a file",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
            ToolParameter("lines", "integer", "Number of lines to show", False, 10),
        ],
        builder=lambda args: ["head", "-n", str(args.get("lines", 10)), args["path"]],
        cacheable=True,
        cache_ttl=0
    ))

    # tail tool
    registry.register(ToolDefinition(
        name="tail",
        description="Display last N lines of a file",
        parameters=[
            ToolParameter("path", "string", "File path to read"),
            ToolParameter("lines", "integer", "Number of lines to show", False, 10),
        ],
        builder=lambda args: ["tail", "-n", str(args.get("lines", 10)), args["path"]],
        cacheable=True,
        cache_ttl=0
    ))

    # ls tool
    registry.register(ToolDefinition(
        name="ls",
        description="List directory contents",
        parameters=[
            ToolParameter("path", "string", "Directory path to list"),
            ToolParameter("all", "boolean", "Show hidden files", False, False),
            ToolParameter("long", "boolean", "Use long format", False, False),
        ],
        builder=lambda args: [
            "ls",
            "-a" if args.get("all", False) else "",
            "-l" if args.get("long", False) else "",
            args["path"]
        ],
        cacheable=False,  # Directory listing changes frequently
        cache_ttl=None
    ))

    # wc tool
    registry.register(ToolDefinition(
        name="wc",
        description="Count lines, words, and characters in a file",
        parameters=[
            ToolParameter("path", "string", "File path to count"),
            ToolParameter("lines", "boolean", "Count lines only", False, False),
            ToolParameter("words", "boolean", "Count words only", False, False),
        ],
        builder=lambda args: [
            "wc",
            "-l" if args.get("lines", False) else "",
            "-w" if args.get("words", False) else "",
            args["path"]
        ],
        cacheable=False,
        cache_ttl=None
    ))

    return registry
```

**Update exports**:

```python
# app/repositories/__init__.py
from app.repositories.base import Repository
from app.repositories.session_repository import Session, SessionRepository
from app.repositories.tool_registry import (
    ToolParameter,
    ToolDefinition,
    ToolRegistry,
    create_default_registry,
)

__all__ = [
    "Repository",
    "Session",
    "SessionRepository",
    "ToolParameter",
    "ToolDefinition",
    "ToolRegistry",
    "create_default_registry",
]
```

---

### Step 2.2: Component Factory (6h)

**Tạo thư mục và files**:
```bash
mkdir -p app/factories
touch app/factories/__init__.py
touch app/factories/component_factory.py
```

**Tasks**:
1. [ ] Tạo abstract `ComponentFactory` base class
2. [ ] Implement `DefaultComponentFactory`
3. [ ] Implement `TestComponentFactory` cho testing

**Code Template**:

```python
# app/factories/component_factory.py
from abc import ABC, abstractmethod
from typing import Optional

from openai import AsyncAzureOpenAI

from app.config.agent_config import (
    OpenAIConfig,
    SandboxConfig,
    CacheConfig,
    OrchestratorConfig,
)
from app.sandbox.executor import SandboxExecutor
from app.agent.orchestrator import ParallelToolOrchestrator
from app.cache.cache_manager import CacheManager

class ComponentFactory(ABC):
    """Abstract factory for agent components"""

    @abstractmethod
    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        """Create Azure OpenAI client"""
        pass

    @abstractmethod
    def create_executor(self, config: SandboxConfig) -> SandboxExecutor:
        """Create sandbox executor"""
        pass

    @abstractmethod
    def create_cache_manager(self, config: CacheConfig) -> Optional[CacheManager]:
        """Create cache manager (None if disabled)"""
        pass

    @abstractmethod
    def create_orchestrator(
        self,
        config: OrchestratorConfig,
        executor: SandboxExecutor
    ) -> ParallelToolOrchestrator:
        """Create tool orchestrator"""
        pass


class DefaultComponentFactory(ComponentFactory):
    """Default factory implementation for production"""

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
    """Factory for testing with mock components"""

    def __init__(
        self,
        mock_client=None,
        mock_executor=None,
        mock_cache_manager=None,
    ):
        self.mock_client = mock_client
        self.mock_executor = mock_executor
        self.mock_cache_manager = mock_cache_manager

    def create_client(self, config: OpenAIConfig) -> AsyncAzureOpenAI:
        if self.mock_client:
            return self.mock_client
        # Return a mock that can be used in tests
        from unittest.mock import AsyncMock, MagicMock
        mock = MagicMock(spec=AsyncAzureOpenAI)
        mock.chat = MagicMock()
        mock.chat.completions = MagicMock()
        mock.chat.completions.create = AsyncMock()
        return mock

    def create_executor(self, config: SandboxConfig) -> SandboxExecutor:
        if self.mock_executor:
            return self.mock_executor
        # Return real executor for integration tests
        return SandboxExecutor(
            root_path=config.root_path,
            timeout=config.timeout,
            max_file_size=config.max_file_size,
            max_output_size=config.max_output_size,
            sandbox_enabled=config.enabled,
        )

    def create_cache_manager(self, config: CacheConfig) -> Optional[CacheManager]:
        if self.mock_cache_manager:
            return self.mock_cache_manager
        if not config.enabled:
            return None
        # Use in-memory cache for tests
        return CacheManager(
            cache_dir="tmp/test_cache",
            size_limit=10 * 1024 * 1024,  # 10MB for tests
            content_ttl=config.content_ttl,
            search_ttl=config.search_ttl,
        )

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
```

---

### Step 2.3: Agent Factory (8h)

**Tạo file**: `app/factories/agent_factory.py`

**Tasks**:
1. [ ] Implement `AgentFactory` class
2. [ ] Add `create()` method
3. [ ] Add `create_from_settings()` method
4. [ ] Add singleton getter

**Code Template**:

```python
# app/factories/agent_factory.py
from typing import Optional

from app.config.agent_config import AgentConfig
from app.config import Settings
from app.factories.component_factory import ComponentFactory, DefaultComponentFactory
from app.repositories.tool_registry import ToolRegistry, create_default_registry
from app.agent.filesystem_agent import FilesystemAgent

class AgentFactory:
    """Factory for creating FilesystemAgent instances"""

    def __init__(
        self,
        component_factory: Optional[ComponentFactory] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.component_factory = component_factory or DefaultComponentFactory()
        self.tool_registry = tool_registry or create_default_registry()

    def create(self, config: AgentConfig) -> FilesystemAgent:
        """Create fully configured agent from config"""
        # Create components using factory
        client = self.component_factory.create_client(config.openai)
        executor = self.component_factory.create_executor(config.sandbox)
        cache_manager = self.component_factory.create_cache_manager(config.cache)
        orchestrator = self.component_factory.create_orchestrator(
            config.orchestrator,
            executor
        )

        # Create agent with all components
        return FilesystemAgent(
            client=client,
            deployment_name=config.openai.deployment_name,
            executor=executor,
            orchestrator=orchestrator,
            cache_manager=cache_manager,
            tool_registry=self.tool_registry,
            max_iterations=config.max_tool_iterations,
            data_root=config.sandbox.root_path,
        )

    def create_from_settings(self, settings: Settings) -> FilesystemAgent:
        """Create agent from application settings"""
        config = AgentConfig.from_settings(settings)
        return self.create(config)


# Singleton instance
_agent_factory: Optional[AgentFactory] = None

def get_agent_factory() -> AgentFactory:
    """Get or create agent factory singleton"""
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()
    return _agent_factory

def reset_agent_factory() -> None:
    """Reset factory singleton (for testing)"""
    global _agent_factory
    _agent_factory = None
```

```python
# app/factories/__init__.py
from app.factories.component_factory import (
    ComponentFactory,
    DefaultComponentFactory,
    TestComponentFactory,
)
from app.factories.agent_factory import (
    AgentFactory,
    get_agent_factory,
    reset_agent_factory,
)

__all__ = [
    "ComponentFactory",
    "DefaultComponentFactory",
    "TestComponentFactory",
    "AgentFactory",
    "get_agent_factory",
    "reset_agent_factory",
]
```

---

### Step 2.4: Refactor FilesystemAgent (12h)

**Tasks**:
1. [ ] Update `FilesystemAgent.__init__()` để accept injected dependencies
2. [ ] Add `tool_registry` parameter
3. [ ] Update tool building to use registry
4. [ ] Remove hardcoded `BASH_TOOLS`
5. [ ] Keep backward compatibility với `create_agent()` function

**Code Changes** (high-level):

```python
# app/agent/filesystem_agent.py - REFACTORED

class FilesystemAgent:
    """Filesystem agent with injected dependencies"""

    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment_name: str,
        executor: SandboxExecutor,
        orchestrator: ParallelToolOrchestrator,
        cache_manager: Optional[CacheManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_iterations: int = 10,
        data_root: Optional[Path] = None,
    ):
        self.client = client
        self.deployment_name = deployment_name
        self.executor = executor
        self.orchestrator = orchestrator
        self.cache_manager = cache_manager
        self.tool_registry = tool_registry or create_default_registry()
        self.max_iterations = max_iterations
        self.data_root = data_root or Path("./data")

    def get_tools(self) -> List[dict]:
        """Get tools in OpenAI format"""
        return self.tool_registry.to_openai_format()

    async def chat(self, message: str, history: List[dict] = None) -> AgentResponse:
        """Main chat method"""
        # Use self.get_tools() instead of BASH_TOOLS
        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            tools=self.get_tools(),
            tool_choice="auto",
        )
        # ... rest of implementation

    def _build_command(self, tool_name: str, arguments: dict) -> List[str]:
        """Build command using tool registry"""
        return self.tool_registry.build_command(tool_name, arguments)


# Keep backward compatible factory function
def create_agent(...) -> FilesystemAgent:
    """Backward compatible factory function"""
    from app.factories.agent_factory import AgentFactory
    from app.config.agent_config import AgentConfig, OpenAIConfig, ...

    config = AgentConfig(
        openai=OpenAIConfig(...),
        sandbox=SandboxConfig(...),
        ...
    )
    factory = AgentFactory()
    return factory.create(config)
```

---

### Step 2.5: Update Dependencies (4h)

**Update**: `app/dependencies.py`

```python
# app/dependencies.py - COMPLETE
from functools import lru_cache
from typing import Optional

from app.config import Settings
from app.repositories.session_repository import SessionRepository
from app.repositories.tool_registry import ToolRegistry, create_default_registry
from app.factories.agent_factory import AgentFactory, get_agent_factory
from app.agent.filesystem_agent import FilesystemAgent

# Settings
@lru_cache()
def get_settings() -> Settings:
    return Settings()

# Session repository singleton
_session_repository: Optional[SessionRepository] = None

def get_session_repository() -> SessionRepository:
    global _session_repository
    if _session_repository is None:
        _session_repository = SessionRepository(ttl_seconds=3600)
    return _session_repository

# Tool registry singleton
_tool_registry: Optional[ToolRegistry] = None

def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = create_default_registry()
    return _tool_registry

# Agent dependency
def get_agent(
    settings: Settings = None,
    factory: AgentFactory = None,
) -> FilesystemAgent:
    """Get configured agent instance"""
    if settings is None:
        settings = get_settings()
    if factory is None:
        factory = get_agent_factory()
    return factory.create_from_settings(settings)

# Reset functions for testing
def reset_dependencies():
    global _session_repository, _tool_registry
    _session_repository = None
    _tool_registry = None
```

---

### Phase 2 Checklist

- [ ] Step 2.1: Tool Registry implemented
- [ ] Step 2.2: Component Factory implemented
- [ ] Step 2.3: Agent Factory implemented
- [ ] Step 2.4: FilesystemAgent refactored
- [ ] Step 2.5: Dependencies updated
- [ ] All tests passing
- [ ] Backward compatibility verified

---

## Phase 3: Cache Improvements (Tuần 5-6)

### Step 3.1: Cache Repository (8h)

**Tạo file**: `app/repositories/cache_repository.py`

**Tasks**:
1. [ ] Tạo abstract `CacheRepository` interface
2. [ ] Implement `DiskCacheRepository`
3. [ ] Implement `MemoryCacheRepository` (for testing)
4. [ ] Add statistics tracking

---

### Step 3.2: Invalidation Strategies (8h)

**Tạo thư mục và files**:
```bash
mkdir -p app/cache/strategies
touch app/cache/strategies/__init__.py
touch app/cache/strategies/invalidation.py
```

**Tasks**:
1. [ ] Tạo `InvalidationStrategy` ABC
2. [ ] Implement `FileStateInvalidation`
3. [ ] Implement `TTLInvalidation`
4. [ ] Implement `CompositeInvalidation`

---

### Step 3.3: Cache Observers (6h)

**Tạo thư mục và files**:
```bash
mkdir -p app/cache/observers
touch app/cache/observers/__init__.py
touch app/cache/observers/cache_observer.py
```

**Tasks**:
1. [ ] Tạo `CacheObserver` ABC
2. [ ] Implement `MetricsObserver`
3. [ ] Implement `LoggingObserver`
4. [ ] Tạo `CacheEventManager`

---

### Step 3.4: Refactor CacheManager (10h)

**Tasks**:
1. [ ] Update `CacheManager` to use `CacheRepository`
2. [ ] Integrate `InvalidationStrategy`
3. [ ] Add `CacheEventManager` support
4. [ ] Update tests

---

### Step 3.5: Add Metrics Collection (4h)

**Tạo file**: `app/cache/metrics.py`

**Tasks**:
1. [ ] Create metrics dataclass
2. [ ] Add Prometheus-compatible export (optional)
3. [ ] Add cache dashboard endpoint

---

### Phase 3 Checklist

- [ ] Step 3.1: Cache Repository implemented
- [ ] Step 3.2: Invalidation Strategies implemented
- [ ] Step 3.3: Cache Observers implemented
- [ ] Step 3.4: CacheManager refactored
- [ ] Step 3.5: Metrics collection added
- [ ] All tests passing

---

## Phase 4: DAG & Handler Chain (Tuần 7-8)

### Step 4.1: Workflow Nodes (10h)

**Tạo thư mục và files**:
```bash
mkdir -p app/workflow
touch app/workflow/__init__.py
touch app/workflow/nodes.py
```

**Tasks**:
1. [ ] Tạo `NodeStatus` enum
2. [ ] Tạo `WorkflowNode` ABC
3. [ ] Implement `ParseNode`
4. [ ] Implement `ValidateNode`
5. [ ] Implement `ExecuteNode`
6. [ ] Implement `CacheNode`

---

### Step 4.2: DAG Executor (12h)

**Tạo file**: `app/workflow/dag_executor.py`

**Tasks**:
1. [ ] Tạo `WorkflowContext` dataclass
2. [ ] Implement `DAGExecutor` class
3. [ ] Implement `build_execution_order()` (topological sort)
4. [ ] Implement `execute()` với parallel layers
5. [ ] Add error handling và cascade skipping

---

### Step 4.3: Workflow Builder (8h)

**Tạo file**: `app/workflow/builder.py`

**Tasks**:
1. [ ] Implement `ToolExecutionWorkflow` builder
2. [ ] Add `add_tool_execution()` method
3. [ ] Handle cache nodes optionally
4. [ ] Add `build()` method

---

### Step 4.4: Tool Handlers - Chain of Responsibility (10h)

**Tạo thư mục và files**:
```bash
mkdir -p app/agent/handlers
touch app/agent/handlers/__init__.py
touch app/agent/handlers/tool_handlers.py
```

**Tasks**:
1. [ ] Tạo `ToolHandler` ABC
2. [ ] Implement `CachedReadHandler`
3. [ ] Implement `CachedSearchHandler`
4. [ ] Implement `DefaultHandler`
5. [ ] Tạo `create_handler_chain()` function

---

### Step 4.5: Integration Testing (8h)

**Tạo file**: `tests/test_workflow.py`

**Tasks**:
1. [ ] Test DAG execution order
2. [ ] Test parallel execution
3. [ ] Test error cascade
4. [ ] Test handler chain

---

### Phase 4 Checklist

- [ ] Step 4.1: Workflow Nodes implemented
- [ ] Step 4.2: DAG Executor implemented
- [ ] Step 4.3: Workflow Builder implemented
- [ ] Step 4.4: Tool Handlers implemented
- [ ] Step 4.5: Integration tests passing
- [ ] All tests passing

---

## Phase 5: Testing & Documentation (Tuần 9-10)

### Step 5.1: Repository Tests (12h)

**Tạo files**:
```bash
touch tests/test_repositories.py
touch tests/test_tool_registry.py
touch tests/test_cache_repository.py
```

**Tasks**:
1. [ ] Test SessionRepository CRUD
2. [ ] Test SessionRepository concurrency
3. [ ] Test ToolRegistry registration
4. [ ] Test CacheRepository operations

---

### Step 5.2: Factory Tests (8h)

**Tạo file**: `tests/test_factories.py`

**Tasks**:
1. [ ] Test ComponentFactory
2. [ ] Test AgentFactory
3. [ ] Test TestComponentFactory với mocks

---

### Step 5.3: Integration Tests (12h)

**Tạo file**: `tests/test_integration_patterns.py`

**Tasks**:
1. [ ] End-to-end agent test với factories
2. [ ] Test cache với observers
3. [ ] Test workflow execution
4. [ ] Test error handling với exception hierarchy

---

### Step 5.4: Performance Benchmarks (8h)

**Tạo file**: `benchmarks/benchmark_patterns.py`

**Tasks**:
1. [ ] Benchmark DAG vs linear execution
2. [ ] Benchmark cache với observers overhead
3. [ ] Benchmark factory creation time
4. [ ] Generate comparison report

---

### Step 5.5: Documentation (8h)

**Update files**:
- `docs/ARCHITECTURE.md` - Updated architecture
- `docs/PATTERNS.md` - Design patterns guide
- `docs/TESTING.md` - Testing guide
- `README.md` - Update main readme

**Tasks**:
1. [ ] Document new architecture
2. [ ] Document design patterns used
3. [ ] Add code examples
4. [ ] Update API documentation

---

### Phase 5 Checklist

- [ ] Step 5.1: Repository tests completed
- [ ] Step 5.2: Factory tests completed
- [ ] Step 5.3: Integration tests completed
- [ ] Step 5.4: Benchmarks completed
- [ ] Step 5.5: Documentation updated
- [ ] Test coverage > 80%
- [ ] All CI checks passing

---

## Quick Reference: File Structure After Implementation

```
app/
├── __init__.py
├── main.py
├── config.py
├── cli.py
├── exceptions.py                    # NEW - Phase 1
├── dependencies.py                  # NEW - Phase 1
│
├── config/                          # NEW - Phase 1
│   ├── __init__.py
│   └── agent_config.py
│
├── repositories/                    # NEW - Phase 1, 2, 3
│   ├── __init__.py
│   ├── base.py
│   ├── session_repository.py
│   ├── tool_registry.py
│   └── cache_repository.py
│
├── factories/                       # NEW - Phase 2
│   ├── __init__.py
│   ├── component_factory.py
│   └── agent_factory.py
│
├── agent/
│   ├── __init__.py
│   ├── filesystem_agent.py          # MODIFIED - Phase 2
│   ├── orchestrator.py
│   ├── prompts.py
│   ├── cache.py
│   ├── handlers/                    # NEW - Phase 4
│   │   ├── __init__.py
│   │   └── tool_handlers.py
│   └── tools/
│       ├── __init__.py
│       ├── bash_tools.py
│       ├── adaptive_reader.py
│       ├── file_tools.py
│       └── streaming.py
│
├── sandbox/
│   ├── __init__.py
│   ├── executor.py                  # MODIFIED - Phase 1 (exceptions)
│   └── cached_executor.py
│
├── cache/
│   ├── __init__.py
│   ├── cache_manager.py             # MODIFIED - Phase 3
│   ├── disk_cache.py
│   ├── content_cache.py
│   ├── search_cache.py
│   ├── file_state.py
│   ├── warmup.py
│   ├── metrics.py                   # NEW - Phase 3
│   ├── strategies/                  # NEW - Phase 3
│   │   ├── __init__.py
│   │   └── invalidation.py
│   └── observers/                   # NEW - Phase 3
│       ├── __init__.py
│       └── cache_observer.py
│
├── workflow/                        # NEW - Phase 4
│   ├── __init__.py
│   ├── nodes.py
│   ├── dag_executor.py
│   └── builder.py
│
└── api/
    ├── __init__.py
    └── routes/
        ├── __init__.py
        ├── chat.py                  # MODIFIED - Phase 1
        ├── stream.py
        └── documents.py

tests/
├── test_exceptions.py               # NEW
├── test_config.py                   # NEW
├── test_repositories.py             # NEW
├── test_session_repository.py       # NEW
├── test_tool_registry.py            # NEW
├── test_cache_repository.py         # NEW
├── test_factories.py                # NEW
├── test_workflow.py                 # NEW
├── test_integration_patterns.py     # NEW
└── ... (existing tests)

benchmarks/
└── benchmark_patterns.py            # NEW

docs/
├── ARCHITECTURE.md                  # NEW/UPDATED
├── PATTERNS.md                      # NEW
└── TESTING.md                       # NEW
```

---

## Execution Commands

```bash
# Phase 1
poetry run pytest tests/test_exceptions.py tests/test_config.py tests/test_session_repository.py -v

# Phase 2
poetry run pytest tests/test_tool_registry.py tests/test_factories.py -v

# Phase 3
poetry run pytest tests/test_cache_repository.py -v

# Phase 4
poetry run pytest tests/test_workflow.py -v

# Phase 5 - All tests
poetry run pytest tests/ -v --cov=app --cov-report=html

# Run benchmarks
poetry run python benchmarks/benchmark_patterns.py
```

---

## Notes

1. **Backward Compatibility**: Giữ `create_agent()` function để không break existing code
2. **Testing**: Viết tests song song với implementation
3. **Incremental**: Mỗi step nên có thể chạy độc lập
4. **CI/CD**: Update CI pipeline sau mỗi phase

---

*Document này cung cấp hướng dẫn chi tiết để triển khai từng design pattern theo thứ tự.*
