# Roadmap Tích Hợp Langfuse & Prometheus - Filesystem Agent Showcase

**Ngày tạo:** 2026-01-23
**Phiên bản:** 1.0
**Tác giả:** Phân tích bởi Claude Code với 4 agents song song

---

## 📋 Mục Lục

1. [Tổng Quan Dự Án](#1-tổng-quan-dự-án)
2. [Phân Tích Kiến Trúc Hiện Tại](#2-phân-tích-kiến-trúc-hiện-tại)
3. [Core Business & Điểm Quan Trọng](#3-core-business--điểm-quan-trọng)
4. [Roadmap Tích Hợp Langfuse](#4-roadmap-tích-hợp-langfuse)
5. [Roadmap Tích Hợp Prometheus](#5-roadmap-tích-hợp-prometheus)
6. [Kế Hoạch Triển Khai](#6-kế-hoạch-triển-khai)
7. [Rủi Ro & Giải Pháp](#7-rủi-ro--giải-pháp)

---

## 1. Tổng Quan Dự Án

### 1.1 Bản Chất Dự Án

**Filesystem Agent Showcase** là một ứng dụng FastAPI demo AI agents sử dụng filesystem/bash tools thay vì RAG pipeline truyền thống. LLM (Azure OpenAI) quyết định bash commands nào cần thực thi, và kết quả được đưa trở lại trong một vòng lặp agentic.

### 1.2 Đặc Điểm Kỹ Thuật Chính

- **Framework:** FastAPI (Python)
- **LLM Provider:** Azure OpenAI (GPT-4)
- **Agent Pattern:** Agentic loop với function calling
- **Tool Execution:** Sandboxed bash commands (grep, find, cat, ls, etc.)
- **Cache System:** Multi-tier persistent cache (v3.0) với disk storage
- **Security:** Whitelist commands + path confinement + timeout protection

### 1.3 Kiến Trúc Tổng Quan

```
User Request
    ↓
FastAPI Routes (/api/chat, /api/documents, /api/stream)
    ↓
FilesystemAgent (chat/chat_stream)
    ↓
[Agentic Loop - Max 10 iterations]
    ├─ LLM Call (Azure OpenAI)
    ├─ Parse Tool Calls
    ├─ Execute Tools (ParallelToolOrchestrator)
    │   ├─ SandboxExecutor (security validation)
    │   └─ CacheManager (v3.0 - content/search caching)
    └─ Feed Results Back to LLM
    ↓
Final Response
```

---

## 2. Phân Tích Kiến Trúc Hiện Tại

### 2.1 Agent Core Business Flow

#### **FilesystemAgent** (`app/agent/filesystem_agent.py`)

**Điểm tích hợp LLM chính:**
- **Line 470:** `chat()` method - Non-streaming LLM call
- **Line 594:** `chat_stream()` method - Streaming LLM call với SSE

**Vòng lặp agentic:**
```python
for iteration in range(max_tool_iterations):  # Max 10 lần
    # 1. LLM call với messages + tool definitions
    response = await self.client.chat.completions.create(...)

    # 2. Parse tool_calls từ LLM response
    if not tool_calls:
        break  # LLM không cần tool nữa, trả về final answer

    # 3. Execute tools (parallel hoặc sequential)
    results = await self._execute_tools(tool_calls)

    # 4. Add results vào messages với role="tool"
    messages.append({"role": "tool", "content": results})

    # 5. Loop lại với updated messages
```

**Dữ liệu cần track:**
- Số lần iteration thực tế vs max_iterations
- Tool nào được gọi mỗi iteration
- Thời gian mỗi LLM call
- Token usage (input/output/total)
- Cache hit/miss cho mỗi tool execution
- Kết quả cuối cùng có thành công không

#### **Tool Execution** (`app/agent/orchestrator.py`)

**ParallelToolOrchestrator** thực hiện:
- **Parallel strategy:** Read-only tools (grep, find, cat) chạy đồng thời (max 5 concurrent)
- **Sequential strategy:** Write tools hoặc khi parallel disabled

**Dữ liệu cần track:**
- Số lượng tools executed per iteration
- Parallel vs sequential strategy usage
- Thời gian execution mỗi tool
- Semaphore wait time (khi queue đầy)
- Tool success/failure rate

#### **Sandbox Security** (`app/sandbox/executor.py`)

**SandboxExecutor** đảm bảo:
- Whitelist commands only
- Path confinement trong DATA_ROOT_PATH
- Timeout protection (default: 30 seconds)
- Output size limits

**Dữ liệu cần track:**
- Command execution time
- Timeout occurrences
- Path traversal attempts (blocked)
- Output size distribution

### 2.2 Cache System (Core Performance)

#### **CacheManager** (`app/cache/cache_manager.py`)

Quản lý 4 components:
1. **PersistentCache** - Disk storage với LRU eviction (500MB limit)
2. **FileStateTracker** - Detect file changes qua mtime/size/hash
3. **ContentCache** - Cache nội dung file (cat/head/tail)
4. **SearchCache** - Cache kết quả search (grep/find) với scope tracking

**Performance hiện tại:**
- 50-150x speedup cho repeated operations
- Cache survives restarts
- Automatic invalidation khi files change

**Dữ liệu cần track:**
- Cache hit/miss rate per operation type
- Cache size và usage percentage
- Invalidation frequency (file vs directory level)
- Staleness detection rate
- Time saved by cache hits

### 2.3 API Layer

#### **Routes** (`app/api/routes/`)

**3 routers chính:**

1. **Chat Router** (`/api/chat`)
   - `POST /api/chat` - Chat với agent
   - `POST /api/chat/stream` - Streaming response (SSE)
   - Session management (in-memory, max 50 messages)

2. **Documents Router** (`/api/documents`)
   - CRUD operations cho files
   - Upload/download với size limits (10MB)
   - Path traversal prevention

3. **Stream Router** (`/api/stream`)
   - Streaming file content
   - Search results streaming

**Dữ liệu cần track:**
- Request/response latency per endpoint
- Request rate per endpoint
- Error rate và error types
- Session count và message count
- File operation success/failure rate

### 2.4 Configuration & Dependencies

#### **Settings** (`app/config.py`)

- Pydantic Settings với environment variables
- Singleton pattern qua `@lru_cache`
- Validate configuration on startup

#### **Dependency Injection**

```python
# FastAPI Depends pattern
def get_settings() -> Settings: ...
def get_agent(settings: Settings = Depends(get_settings)) -> FilesystemAgent: ...
```

**Lifespan Manager:**
- Startup: Load settings, initialize components
- Shutdown: Cleanup, flush logs

---

## 3. Core Business & Điểm Quan Trọng

### 3.1 Business Logic Cốt Lõi

#### **Giá Trị Cốt Lõi:**
Ứng dụng demo một cách tiếp cận mới cho AI agents:
- **Thay vì RAG:** Agent tự quyết định bash commands để explore filesystem
- **Performance:** Multi-tier cache giảm latency 50-150x
- **Security:** Sandboxed execution với strict validation

#### **Use Cases Chính:**
1. **Codebase exploration** - Agent tự tìm files, grep code, đọc documentation
2. **Document search** - Intelligent search với context understanding
3. **Data analysis** - Analyze file structures, find patterns
4. **Streaming responses** - Real-time feedback cho user

### 3.2 Metrics Quan Trọng Nhất (Priority Order)

#### **Tier 1: Critical Business Metrics**

1. **LLM Call Success Rate**
   - Metric: `llm_calls_total{status="success|error"}`
   - Why: Core business - nếu LLM fails, toàn bộ agent fails
   - Target: >99.5% success rate

2. **Agent Completion Rate**
   - Metric: `agent_completions_total{status="success|max_iterations|error"}`
   - Why: Đo lường agent có đạt được final answer không
   - Target: <5% max_iterations reached

3. **Cache Hit Rate**
   - Metric: `cache_hits_total / (cache_hits_total + cache_misses_total)`
   - Why: Cache là key performance differentiator
   - Target: >80% hit rate for repeated queries

4. **End-to-End Latency**
   - Metric: `chat_duration_seconds{p50, p95, p99}`
   - Why: User experience metric
   - Target: p95 < 5 seconds (với cache hits)

#### **Tier 2: Operational Metrics**

5. **Tool Execution Success Rate**
   - Metric: `tool_executions_total{tool_name, status}`
   - Why: Detect sandbox issues, command failures
   - Target: >95% success rate

6. **Token Usage & Cost**
   - Metric: `llm_tokens_total{type="input|output|total"}`
   - Why: Cost management (Azure OpenAI pricing)
   - Target: Track trends, set budgets

7. **Parallel Execution Efficiency**
   - Metric: `parallel_tools_executed / total_tools_executed`
   - Why: Measure performance optimization impact
   - Target: >70% tools executed in parallel

#### **Tier 3: Debugging & Optimization Metrics**

8. **Iteration Distribution**
   - Metric: `agent_iterations{count}`
   - Why: Understand agent reasoning complexity
   - Target: Median < 3 iterations

9. **Cache Invalidation Rate**
   - Metric: `cache_invalidations_total{reason}`
   - Why: Optimize cache effectiveness
   - Target: <10% invalidations due to file changes

10. **Error Types Distribution**
    - Metric: `errors_total{error_type, component}`
    - Why: Identify failure patterns
    - Target: Zero PathTraversal, Timeout < 1%

### 3.3 Langfuse vs Prometheus - Phân Chia Trách Nhiệm

| Aspect | Langfuse | Prometheus |
|--------|----------|------------|
| **LLM Tracing** | ✅ Chi tiết mỗi call (messages, tokens, latency) | ❌ Chỉ aggregated metrics |
| **Conversation Flow** | ✅ Full trace của agent iterations | ❌ Không có conversation context |
| **Cost Tracking** | ✅ Token usage breakdown per request | ⚠️ Aggregated totals only |
| **Tool Execution** | ✅ Trace từng tool call với arguments | ⚠️ Aggregated counts và timings |
| **System Performance** | ❌ Không theo dõi infra metrics | ✅ CPU, memory, disk, network |
| **Real-time Monitoring** | ❌ Near real-time, có lag | ✅ Real-time metrics scraping |
| **Alerting** | ❌ Limited alerting | ✅ Prometheus Alertmanager integration |
| **Long-term Trends** | ⚠️ Data retention có giới hạn | ✅ Long-term time series storage |
| **User Sessions** | ✅ Session-level tracing | ❌ Không có session context |

**Kết luận:**
- **Langfuse:** Deep dive vào LLM behavior, debugging specific requests, cost analysis
- **Prometheus:** System health, performance trends, alerting, operational monitoring

---

## 4. Roadmap Tích Hợp Langfuse

### 4.1 Mục Tiêu Langfuse Integration

**Objectives:**
1. Track mỗi LLM call với đầy đủ context (messages, tokens, latency)
2. Trace complete agent execution flow (iterations, tool calls, results)
3. Monitor token usage và estimate costs per request
4. Debug failed or inefficient agent runs
5. Analyze agent reasoning patterns và tool usage

### 4.2 Kiến Trúc Langfuse Integration

```
User Request
    ↓
[Langfuse Trace Start] ← Session ID, user message
    ↓
Iteration 1
    ├─ [LLM Span] ← Messages, model, temperature
    │   └─ [Output] Tokens used, response content, tool_calls
    ├─ [Tool Execution Span - Parallel]
    │   ├─ [grep Span] ← Pattern, path, output
    │   ├─ [find Span] ← Name pattern, results
    │   └─ [cat Span] ← File path, cache hit, content length
    └─ [Tool Results] → Back to LLM
    ↓
Iteration 2
    └─ [Similar structure]
    ↓
[Trace End] ← Final response, total iterations, total tokens, total time
```

### 4.3 Implementation Steps

#### **Phase 1: Setup & Configuration (Priority: HIGH)**

**Task 1.1: Add Langfuse Dependencies**
```bash
# pyproject.toml
langfuse = "^2.48.0"
langfuse-openai = "^2.0.0"  # OpenAI client wrapper
```

**Task 1.2: Update Settings** (`app/config.py`)
```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Langfuse Configuration
    langfuse_enabled: bool = False
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str = "production"  # or development
    langfuse_release: str = "0.1.0"
    langfuse_sample_rate: float = 1.0  # Sample 100% initially
```

**Task 1.3: Update .env.example**
```bash
# Langfuse Configuration (Optional)
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENVIRONMENT=development
LANGFUSE_RELEASE=0.1.0
LANGFUSE_SAMPLE_RATE=1.0
```

**Estimated Time:** 1 hour
**Risk:** Low - Configuration only

---

#### **Phase 2: Langfuse Client Initialization (Priority: HIGH)**

**Task 2.1: Create Langfuse Manager** (`app/observability/langfuse_manager.py`)
```python
"""Langfuse integration manager."""

from typing import Optional
from langfuse import Langfuse
from app.config import Settings
import logging

logger = logging.getLogger(__name__)

class LangfuseManager:
    """Manages Langfuse client lifecycle."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[Langfuse] = None

    def initialize(self) -> Optional[Langfuse]:
        """Initialize Langfuse client if enabled."""
        if not self.settings.langfuse_enabled:
            logger.info("Langfuse disabled - skipping initialization")
            return None

        if not self.settings.langfuse_public_key or not self.settings.langfuse_secret_key:
            logger.warning("Langfuse enabled but credentials missing")
            return None

        try:
            self._client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
                environment=self.settings.langfuse_environment,
                release=self.settings.langfuse_release,
                sample_rate=self.settings.langfuse_sample_rate,
            )
            logger.info(f"Langfuse initialized: {self.settings.langfuse_host}")
            return self._client
        except Exception as e:
            logger.exception(f"Failed to initialize Langfuse: {e}")
            return None

    def shutdown(self):
        """Flush pending traces on shutdown."""
        if self._client:
            logger.info("Flushing Langfuse traces...")
            self._client.flush()
            logger.info("Langfuse shutdown complete")

    @property
    def client(self) -> Optional[Langfuse]:
        """Get Langfuse client."""
        return self._client
```

**Task 2.2: Update Application Lifespan** (`app/main.py`)
```python
from app.observability.langfuse_manager import LangfuseManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("Starting Filesystem Agent Showcase")

    # Initialize Langfuse
    langfuse_manager = LangfuseManager(settings)
    langfuse_client = langfuse_manager.initialize()
    app.state.langfuse = langfuse_client

    # Ensure data directory exists
    data_root = Path(settings.data_root_path)
    data_root.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data root: {data_root}")

    yield

    # Shutdown
    langfuse_manager.shutdown()
    logger.info("Application shutdown complete")
```

**Estimated Time:** 2 hours
**Risk:** Low - Lifecycle management

---

#### **Phase 3: Agent-Level Tracing (Priority: HIGH)**

**Task 3.1: Add Trace Context to FilesystemAgent** (`app/agent/filesystem_agent.py`)

Thêm trace context parameter:
```python
from typing import Optional
from langfuse.client import StatefulTraceClient

class FilesystemAgent:
    # ... existing code ...

    async def chat(
        self,
        user_message: str,
        history: Optional[list[dict]] = None,
        trace: Optional[StatefulTraceClient] = None,  # NEW
    ) -> AgentResponse:
        """Process user message and return agent response."""
        # Create trace if not provided
        if trace is None and hasattr(self, "langfuse_client") and self.langfuse_client:
            trace = self.langfuse_client.trace(
                name="agent_chat",
                input={"message": user_message},
                user_id=None,  # Can add user_id if available
            )

        messages = self._build_messages(user_message, history)
        tool_calls_history = []
        tool_results_history = []

        try:
            for iteration in range(self.max_tool_iterations):
                logger.info(f"Agent iteration {iteration + 1}/{self.max_tool_iterations}")

                # Create iteration span
                if trace:
                    iteration_span = trace.span(
                        name=f"iteration_{iteration + 1}",
                        input={"messages_count": len(messages)},
                    )

                # LLM Call with tracing
                llm_span = iteration_span.span(name="llm_call") if trace else None
                response = await self._traced_llm_call(messages, llm_span)

                # Parse tool calls
                tool_calls = self._parse_tool_calls(response)
                if not tool_calls:
                    # Final response
                    final_message = response.choices[0].message.content or ""
                    if trace:
                        trace.update(output={"message": final_message})
                    return AgentResponse(
                        message=final_message,
                        tool_calls=tool_calls_history,
                        tool_results=tool_results_history,
                    )

                # Execute tools with tracing
                results = await self._traced_tool_execution(
                    tool_calls,
                    iteration_span if trace else None
                )

                # Update messages
                messages.append(...)  # Add assistant message
                for result in results:
                    messages.append(...)  # Add tool results

                tool_calls_history.extend(tool_calls)
                tool_results_history.extend(results)

            # Max iterations reached
            logger.warning("Max tool iterations reached")
            if trace:
                trace.update(
                    output={"error": "Max iterations reached"},
                    metadata={"max_iterations": self.max_tool_iterations},
                )
            # ... return response

        except Exception as e:
            logger.exception(f"Error in agent chat: {e}")
            if trace:
                trace.update(
                    output={"error": str(e)},
                    level="ERROR",
                )
            raise
```

**Task 3.2: LLM Call Tracing**
```python
async def _traced_llm_call(
    self,
    messages: list[dict],
    span: Optional[StatefulSpanClient] = None,
) -> ChatCompletion:
    """Execute LLM call with tracing."""
    start_time = time.time()

    try:
        if span:
            span.update(
                input={
                    "messages": messages,
                    "model": self.deployment_name,
                    "tools_count": len(BASH_TOOLS),
                },
            )

        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            tools=BASH_TOOLS,
            tool_choice="auto",
        )

        # Extract token usage
        usage = response.usage
        duration = time.time() - start_time

        if span:
            span.update(
                output={
                    "content": response.choices[0].message.content,
                    "tool_calls_count": len(response.choices[0].message.tool_calls or []),
                },
                metadata={
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "completion_tokens": usage.completion_tokens if usage else None,
                    "total_tokens": usage.total_tokens if usage else None,
                    "duration_seconds": duration,
                },
            )

        return response

    except Exception as e:
        if span:
            span.update(
                output={"error": str(e)},
                level="ERROR",
            )
        raise
```

**Task 3.3: Tool Execution Tracing**
```python
async def _traced_tool_execution(
    self,
    tool_calls: list[ToolCall],
    parent_span: Optional[StatefulSpanClient] = None,
) -> list[dict]:
    """Execute tools with tracing."""
    tools_span = parent_span.span(name="tool_execution") if parent_span else None

    if tools_span:
        tools_span.update(
            input={
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments}
                    for tc in tool_calls
                ],
                "count": len(tool_calls),
            },
        )

    results = []
    for tool_call in tool_calls:
        # Create span per tool
        tool_span = tools_span.span(name=f"tool_{tool_call.name}") if tools_span else None

        if tool_span:
            tool_span.update(
                input={
                    "tool_id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )

        start_time = time.time()

        try:
            # Execute tool (with caching)
            result = await self._execute_tool(tool_call)
            duration = time.time() - start_time

            if tool_span:
                tool_span.update(
                    output={
                        "success": result["success"],
                        "output_length": len(result.get("output", "")),
                        "cached": result.get("cached", False),
                    },
                    metadata={
                        "duration_seconds": duration,
                        "return_code": result.get("return_code"),
                        "cache_hit": result.get("cached", False),
                    },
                )

            results.append(result)

        except Exception as e:
            if tool_span:
                tool_span.update(
                    output={"error": str(e)},
                    level="ERROR",
                )
            # Re-raise or handle error
            results.append({"success": False, "error": str(e)})

    if tools_span:
        success_count = sum(1 for r in results if r.get("success"))
        tools_span.update(
            output={
                "total": len(results),
                "success": success_count,
                "failed": len(results) - success_count,
            },
        )

    return results
```

**Estimated Time:** 8 hours
**Risk:** Medium - Requires careful integration into agent loop

---

#### **Phase 4: API Route Integration (Priority: MEDIUM)**

**Task 4.1: Update Chat Endpoint** (`app/api/routes/chat.py`)
```python
from langfuse import Langfuse
from typing import Optional

def get_langfuse_client(request: Request) -> Optional[Langfuse]:
    """Get Langfuse client from app state."""
    return getattr(request.app.state, "langfuse", None)

@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    http_request: Request,
    agent: FilesystemAgent = Depends(get_agent),
    langfuse: Optional[Langfuse] = Depends(get_langfuse_client),
):
    """Chat endpoint with Langfuse tracing."""
    # Create root trace
    trace = None
    if langfuse:
        trace = langfuse.trace(
            name="chat_request",
            input={
                "message": request.message,
                "session_id": request.session_id,
            },
            user_id=request.session_id,  # Use session_id as user identifier
            metadata={
                "endpoint": "/api/chat",
                "method": "POST",
            },
        )

    try:
        # Get or create session history
        session_id = request.session_id or str(uuid.uuid4())
        history = _sessions.get(session_id, [])

        # Call agent with trace context
        response = await agent.chat(
            user_message=request.message,
            history=history,
            trace=trace,  # Pass trace to agent
        )

        # Update session
        _sessions[session_id] = history + [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": response.message},
        ]

        # Update trace with final output
        if trace:
            trace.update(
                output={
                    "response": response.message,
                    "tool_calls_count": len(response.tool_calls),
                    "session_id": session_id,
                },
            )

        return ChatResponse(
            response=response.message,
            session_id=session_id,
            tool_calls=[...],
            tool_results=[...],
        )

    except Exception as e:
        logger.exception(f"Error processing chat request: {e}")
        if trace:
            trace.update(
                output={"error": str(e)},
                level="ERROR",
            )
        raise HTTPException(status_code=500, detail=str(e))
```

**Task 4.2: Update Streaming Endpoint**
```python
@router.post("/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    agent: FilesystemAgent = Depends(get_agent),
    langfuse: Optional[Langfuse] = Depends(get_langfuse_client),
):
    """Streaming chat endpoint with Langfuse tracing."""
    trace = None
    if langfuse:
        trace = langfuse.trace(
            name="chat_stream",
            input={"message": request.message, "session_id": request.session_id},
            user_id=request.session_id,
        )

    async def event_generator():
        try:
            session_id = request.session_id or str(uuid.uuid4())
            history = _sessions.get(session_id, [])

            # Stream events from agent
            async for event in agent.chat_stream(
                user_message=request.message,
                history=history,
                trace=trace,  # Pass trace
            ):
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"

            # Final event
            yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"

        except Exception as e:
            logger.exception(f"Error in streaming: {e}")
            if trace:
                trace.update(output={"error": str(e)}, level="ERROR")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Estimated Time:** 4 hours
**Risk:** Low - Straightforward integration

---

#### **Phase 5: Testing & Validation (Priority: HIGH)**

**Task 5.1: Unit Tests for Langfuse Manager**
```python
# tests/test_langfuse_manager.py
import pytest
from app.observability.langfuse_manager import LangfuseManager
from app.config import Settings

def test_langfuse_disabled():
    """Test Langfuse is skipped when disabled."""
    settings = Settings(langfuse_enabled=False)
    manager = LangfuseManager(settings)
    client = manager.initialize()
    assert client is None

def test_langfuse_missing_credentials():
    """Test Langfuse handles missing credentials."""
    settings = Settings(
        langfuse_enabled=True,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )
    manager = LangfuseManager(settings)
    client = manager.initialize()
    assert client is None

@pytest.mark.integration
def test_langfuse_initialization():
    """Test Langfuse initializes with valid credentials."""
    settings = Settings(
        langfuse_enabled=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_host="https://cloud.langfuse.com",
    )
    manager = LangfuseManager(settings)
    client = manager.initialize()
    assert client is not None
    manager.shutdown()
```

**Task 5.2: Integration Tests**
```python
# tests/test_agent_langfuse_integration.py
import pytest
from app.agent.filesystem_agent import create_agent
from langfuse import Langfuse

@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_with_langfuse_trace(tmp_path):
    """Test agent creates Langfuse traces."""
    # Setup
    langfuse = Langfuse(
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host="https://cloud.langfuse.com",
    )

    agent = create_agent(
        api_key="test-key",
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4",
        api_version="2024-02-15-preview",
        data_root=tmp_path,
    )

    # Create trace
    trace = langfuse.trace(name="test_trace", input={"message": "test"})

    # Execute agent
    response = await agent.chat(
        user_message="List files in current directory",
        trace=trace,
    )

    # Validate
    assert response.message != ""
    assert len(response.tool_calls) > 0

    # Flush traces
    langfuse.flush()
```

**Task 5.3: Manual Validation**
- Test với Langfuse cloud dashboard
- Verify traces xuất hiện
- Check token counting accuracy
- Validate trace relationships (parent-child spans)

**Estimated Time:** 6 hours
**Risk:** Medium - Requires Langfuse account setup

---

### 4.4 Langfuse Dashboard Setup

**Task 6.1: Create Langfuse Project**
1. Sign up at https://cloud.langfuse.com
2. Create new project: "Filesystem Agent Showcase"
3. Get API keys (public + secret)
4. Configure environment: Development, Staging, Production

**Task 6.2: Configure Dashboards**
1. **Agent Performance Dashboard:**
   - Avg iterations per request
   - Avg tokens per request
   - Avg latency per request
   - Success rate

2. **Cost Tracking Dashboard:**
   - Total tokens (input/output)
   - Estimated cost (based on Azure pricing)
   - Cost per session
   - Cost trends over time

3. **Tool Usage Dashboard:**
   - Tool call frequency
   - Tool execution success rate
   - Most used tools
   - Cache hit rate per tool

**Task 6.3: Set Up Alerts**
- High error rate (>5%)
- High latency (p95 > 10s)
- High cost (>$X per day)
- Max iterations frequently reached

**Estimated Time:** 2 hours
**Risk:** Low - Configuration only

---

### 4.5 Langfuse Integration Summary

**Total Estimated Time:** 23 hours (~3 days)

**Priority Breakdown:**
- **Phase 1-3:** Critical - Core tracing functionality
- **Phase 4:** Important - API integration
- **Phase 5:** Critical - Testing and validation

**Expected Benefits:**
- Deep visibility into agent behavior
- Token usage tracking và cost estimation
- Debug failed agent runs
- Identify inefficient reasoning patterns
- Session-level analysis

---

## 5. Roadmap Tích Hợp Prometheus

### 5.1 Mục Tiêu Prometheus Integration

**Objectives:**
1. Monitor system performance (CPU, memory, disk)
2. Track API request rate, latency, error rate
3. Monitor cache performance metrics
4. Alert on anomalies và performance degradation
5. Long-term trend analysis

### 5.2 Kiến Trúc Prometheus Integration

```
FastAPI Application
    ├─ PrometheusMiddleware (auto-instrument all endpoints)
    ├─ Custom Metrics (app/metrics.py)
    │   ├─ Counters: requests, errors, cache hits/misses
    │   ├─ Histograms: latency, tool execution time
    │   └─ Gauges: active sessions, cache size
    ↓
Prometheus /metrics endpoint (OpenMetrics format)
    ↓
Prometheus Server (scrapes every 15s)
    ├─ Time Series Database
    ├─ Alertmanager (alerts)
    └─ Grafana (visualization)
```

### 5.3 Implementation Steps

#### **Phase 1: Dependencies & Configuration (Priority: HIGH)**

**Task 1.1: Add Prometheus Dependencies**
```bash
# pyproject.toml
prometheus-client = "^0.20.0"
prometheus-fastapi-instrumentator = "^6.1.0"
```

**Task 1.2: Update Settings** (`app/config.py`)
```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Prometheus Configuration
    prometheus_enabled: bool = True  # Enabled by default
    prometheus_metrics_path: str = "/metrics"
    prometheus_exclude_paths: list[str] = ["/health", "/metrics"]
    prometheus_buckets: list[float] = [0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
```

**Task 1.3: Update .env.example**
```bash
# Prometheus Configuration
PROMETHEUS_ENABLED=true
PROMETHEUS_METRICS_PATH=/metrics
PROMETHEUS_EXCLUDE_PATHS=/health,/metrics
PROMETHEUS_BUCKETS=0.01,0.05,0.1,0.5,1.0,5.0,10.0
```

**Estimated Time:** 1 hour
**Risk:** Low

---

#### **Phase 2: Core Metrics Definition (Priority: HIGH)**

**Task 2.1: Create Metrics Module** (`app/metrics.py`)
```python
"""Prometheus metrics definitions."""

from prometheus_client import Counter, Histogram, Gauge, Info

# API Request Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0),
)

http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"],
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint"],
)

# Agent Metrics
agent_iterations_total = Histogram(
    "agent_iterations_total",
    "Number of iterations per agent execution",
    buckets=(1, 2, 3, 4, 5, 7, 10),
)

agent_completions_total = Counter(
    "agent_completions_total",
    "Total agent completions",
    ["status"],  # success, max_iterations, error
)

agent_execution_duration_seconds = Histogram(
    "agent_execution_duration_seconds",
    "Agent execution duration in seconds",
    ["status"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

# LLM Metrics
llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["status"],  # success, error
)

llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "LLM API call duration in seconds",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens used",
    ["type"],  # input, output, total
)

llm_tokens_per_request = Histogram(
    "llm_tokens_per_request",
    "Tokens per LLM request",
    ["type"],
    buckets=(10, 50, 100, 500, 1000, 2000, 4000, 8000),
)

# Tool Execution Metrics
tool_executions_total = Counter(
    "tool_executions_total",
    "Total tool executions",
    ["tool_name", "status"],  # success, error, timeout
)

tool_execution_duration_seconds = Histogram(
    "tool_execution_duration_seconds",
    "Tool execution duration in seconds",
    ["tool_name"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

parallel_tool_executions_total = Counter(
    "parallel_tool_executions_total",
    "Total parallel tool executions",
)

sequential_tool_executions_total = Counter(
    "sequential_tool_executions_total",
    "Total sequential tool executions",
)

# Cache Metrics
cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "cache_type", "result"],  # get/set/delete, content/search, hit/miss/error
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Current cache size in bytes",
    ["cache_type"],  # disk, content, search
)

cache_entries_total = Gauge(
    "cache_entries_total",
    "Current number of cache entries",
    ["cache_type"],
)

cache_invalidations_total = Counter(
    "cache_invalidations_total",
    "Total cache invalidations",
    ["cache_type", "reason"],  # file_change, directory_change, manual, ttl_expired
)

cache_operation_duration_seconds = Histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["operation", "cache_type"],
    buckets=(0.0001, 0.001, 0.01, 0.05, 0.1, 0.5),
)

# Sandbox Execution Metrics
sandbox_executions_total = Counter(
    "sandbox_executions_total",
    "Total sandbox command executions",
    ["command", "status"],  # success, error, timeout
)

sandbox_execution_duration_seconds = Histogram(
    "sandbox_execution_duration_seconds",
    "Sandbox execution duration in seconds",
    ["command"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0),
)

sandbox_timeouts_total = Counter(
    "sandbox_timeouts_total",
    "Total sandbox execution timeouts",
    ["command"],
)

sandbox_security_blocks_total = Counter(
    "sandbox_security_blocks_total",
    "Total security blocks",
    ["block_type"],  # path_traversal, command_not_allowed, file_too_large
)

# Session Metrics
active_sessions_total = Gauge(
    "active_sessions_total",
    "Current number of active sessions",
)

session_messages_total = Histogram(
    "session_messages_total",
    "Number of messages per session",
    buckets=(1, 5, 10, 20, 50),
)

# Application Info
app_info = Info(
    "app_info",
    "Application information",
)
```

**Estimated Time:** 2 hours
**Risk:** Low - Metric definitions

---

#### **Phase 3: Instrumentation (Priority: HIGH)**

**Task 3.1: FastAPI Middleware** (`app/middleware/prometheus.py`)
```python
"""Prometheus middleware for FastAPI."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_request_size_bytes,
    http_response_size_bytes,
)
import time
import logging

logger = logging.getLogger(__name__)

class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics."""

    def __init__(self, app, exclude_paths: list[str] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or []

    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics."""
        # Skip excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Collect request metrics
        method = request.method
        endpoint = request.url.path

        # Request size
        content_length = request.headers.get("content-length")
        if content_length:
            http_request_size_bytes.labels(method=method, endpoint=endpoint).observe(
                int(content_length)
            )

        # Execute request
        start_time = time.time()
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            status = 500
            logger.exception(f"Error processing request: {e}")
            raise
        finally:
            # Request duration
            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            # Request count
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status,
            ).inc()

        # Response size (if available)
        if hasattr(response, "body"):
            http_response_size_bytes.labels(
                method=method,
                endpoint=endpoint,
            ).observe(len(response.body))

        return response
```

**Task 3.2: Update main.py**
```python
from app.middleware.prometheus import PrometheusMiddleware
from prometheus_client import make_asgi_app, REGISTRY
from app.metrics import app_info

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("Starting Filesystem Agent Showcase")

    # Set app info
    app_info.info({
        "version": "1.0.0",
        "environment": settings.langfuse_environment if hasattr(settings, "langfuse_environment") else "production",
        "azure_openai_deployment": settings.azure_openai_deployment_name,
    })

    # ... existing initialization ...

    yield

    # ... existing shutdown ...

# Create FastAPI app
app = FastAPI(...)

# Add Prometheus middleware
settings = get_settings()
if settings.prometheus_enabled:
    app.add_middleware(
        PrometheusMiddleware,
        exclude_paths=settings.prometheus_exclude_paths,
    )
    logger.info("Prometheus middleware enabled")

# Mount Prometheus metrics endpoint
if settings.prometheus_enabled:
    metrics_app = make_asgi_app(registry=REGISTRY)
    app.mount(settings.prometheus_metrics_path, metrics_app)
    logger.info(f"Prometheus metrics: {settings.prometheus_metrics_path}")
```

**Estimated Time:** 3 hours
**Risk:** Low - Standard middleware pattern

---

#### **Phase 4: Agent & Tool Instrumentation (Priority: HIGH)**

**Task 4.1: Instrument FilesystemAgent** (`app/agent/filesystem_agent.py`)
```python
from app.metrics import (
    agent_iterations_total,
    agent_completions_total,
    agent_execution_duration_seconds,
    llm_calls_total,
    llm_call_duration_seconds,
    llm_tokens_total,
    llm_tokens_per_request,
)
import time

async def chat(
    self,
    user_message: str,
    history: Optional[list[dict]] = None,
    trace: Optional[StatefulTraceClient] = None,
) -> AgentResponse:
    """Process user message and return agent response."""
    start_time = time.time()
    iteration_count = 0
    status = "success"

    try:
        messages = self._build_messages(user_message, history)
        tool_calls_history = []
        tool_results_history = []

        for iteration in range(self.max_tool_iterations):
            iteration_count = iteration + 1
            logger.info(f"Agent iteration {iteration_count}/{self.max_tool_iterations}")

            # LLM Call
            llm_start = time.time()
            try:
                response = await self.client.chat.completions.create(...)
                llm_duration = time.time() - llm_start

                # Track LLM metrics
                llm_calls_total.labels(status="success").inc()
                llm_call_duration_seconds.observe(llm_duration)

                # Track tokens
                if response.usage:
                    llm_tokens_total.labels(type="input").inc(response.usage.prompt_tokens)
                    llm_tokens_total.labels(type="output").inc(response.usage.completion_tokens)
                    llm_tokens_total.labels(type="total").inc(response.usage.total_tokens)

                    llm_tokens_per_request.labels(type="input").observe(response.usage.prompt_tokens)
                    llm_tokens_per_request.labels(type="output").observe(response.usage.completion_tokens)
                    llm_tokens_per_request.labels(type="total").observe(response.usage.total_tokens)

            except Exception as e:
                llm_calls_total.labels(status="error").inc()
                raise

            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)
            if not tool_calls:
                # Success - final answer
                break

            # Execute tools
            results = await self._execute_tools(tool_calls)

            # ... rest of implementation ...

        else:
            # Max iterations reached
            status = "max_iterations"
            logger.warning("Max tool iterations reached")

        # Track agent metrics
        agent_iterations_total.observe(iteration_count)
        agent_completions_total.labels(status=status).inc()

        return AgentResponse(...)

    except Exception as e:
        status = "error"
        agent_completions_total.labels(status="error").inc()
        raise

    finally:
        # Track agent execution time
        duration = time.time() - start_time
        agent_execution_duration_seconds.labels(status=status).observe(duration)
```

**Task 4.2: Instrument Tool Execution**
```python
from app.metrics import (
    tool_executions_total,
    tool_execution_duration_seconds,
    parallel_tool_executions_total,
    sequential_tool_executions_total,
)

async def _execute_tool(self, tool_call: ToolCall) -> dict:
    """Execute a single tool with metrics."""
    start_time = time.time()
    status = "success"

    try:
        # ... existing tool execution logic ...

        result = await self.sandbox.execute(command)

        if not result.success:
            status = "error"

        return {
            "id": tool_call.id,
            "name": tool_call.name,
            "success": result.success,
            "output": result.stdout or result.stderr,
            "return_code": result.return_code,
        }

    except Exception as e:
        status = "error"
        raise

    finally:
        duration = time.time() - start_time
        tool_executions_total.labels(
            tool_name=tool_call.name,
            status=status,
        ).inc()
        tool_execution_duration_seconds.labels(
            tool_name=tool_call.name,
        ).observe(duration)
```

**Task 4.3: Instrument Parallel Orchestrator**
```python
from app.metrics import (
    parallel_tool_executions_total,
    sequential_tool_executions_total,
)

async def execute_with_strategy(self, tool_calls: list[ToolCall]) -> list[dict]:
    """Execute tools with parallel or sequential strategy."""
    if self.parallel_execution and all(is_read_only(tc.name) for tc in tool_calls):
        # Parallel execution
        parallel_tool_executions_total.inc(len(tool_calls))
        return await self._execute_parallel(tool_calls)
    else:
        # Sequential execution
        sequential_tool_executions_total.inc(len(tool_calls))
        return await self._execute_sequential(tool_calls)
```

**Task 4.4: Instrument Sandbox Executor**
```python
from app.metrics import (
    sandbox_executions_total,
    sandbox_execution_duration_seconds,
    sandbox_timeouts_total,
    sandbox_security_blocks_total,
)

async def execute(self, command: str) -> ExecutionResult:
    """Execute command with security checks and metrics."""
    start_time = time.time()
    cmd_name = command.split()[0] if command else "unknown"
    status = "success"

    try:
        # Security checks
        if not self._is_allowed_command(command):
            sandbox_security_blocks_total.labels(block_type="command_not_allowed").inc()
            raise CommandNotAllowedError(...)

        if self._has_path_traversal(command):
            sandbox_security_blocks_total.labels(block_type="path_traversal").inc()
            raise PathTraversalError(...)

        # Execute
        result = await self._run_subprocess(command)

        if result.return_code != 0:
            status = "error"

        return result

    except asyncio.TimeoutError:
        status = "timeout"
        sandbox_timeouts_total.labels(command=cmd_name).inc()
        raise

    except Exception as e:
        status = "error"
        raise

    finally:
        duration = time.time() - start_time
        sandbox_executions_total.labels(command=cmd_name, status=status).inc()
        sandbox_execution_duration_seconds.labels(command=cmd_name).observe(duration)
```

**Estimated Time:** 6 hours
**Risk:** Medium - Requires careful placement of metrics

---

#### **Phase 5: Cache Metrics (Priority: MEDIUM)**

**Task 5.1: Instrument CacheManager**
```python
from app.metrics import (
    cache_operations_total,
    cache_size_bytes,
    cache_entries_total,
    cache_invalidations_total,
    cache_operation_duration_seconds,
)

class CacheManager:
    """Unified cache interface with metrics."""

    async def get_content(
        self,
        file_path: Path,
        loader: Callable,
        ttl: float = 0,
    ) -> str:
        """Get file content with caching and metrics."""
        start_time = time.time()
        cache_type = "content"
        result = "miss"

        try:
            content = await self.content_cache.get_content(file_path, loader, ttl)
            result = "hit" if hasattr(self, "_last_was_hit") and self._last_was_hit else "miss"
            return content

        except Exception as e:
            result = "error"
            raise

        finally:
            duration = time.time() - start_time
            cache_operations_total.labels(
                operation="get",
                cache_type=cache_type,
                result=result,
            ).inc()
            cache_operation_duration_seconds.labels(
                operation="get",
                cache_type=cache_type,
            ).observe(duration)

    async def invalidate_file(self, file_path: Path):
        """Invalidate file with metrics."""
        await self.content_cache.invalidate(file_path)
        await self.search_cache.invalidate_pattern(file_path)

        cache_invalidations_total.labels(
            cache_type="content",
            reason="file_change",
        ).inc()
        cache_invalidations_total.labels(
            cache_type="search",
            reason="file_change",
        ).inc()

    def update_cache_size_metrics(self):
        """Update cache size gauge metrics."""
        stats = self.stats()

        # Update gauges
        cache_size_bytes.labels(cache_type="disk").set(stats["disk_cache"]["volume"])
        cache_entries_total.labels(cache_type="disk").set(stats["disk_cache"]["size"])
```

**Task 5.2: Periodic Cache Stats Collection**
```python
# In main.py lifespan
import asyncio

async def collect_cache_stats_periodically(agent: FilesystemAgent):
    """Collect cache stats every 60 seconds."""
    while True:
        try:
            if agent.cache_manager:
                agent.cache_manager.update_cache_size_metrics()
        except Exception as e:
            logger.exception(f"Error collecting cache stats: {e}")

        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # ... existing initialization ...

    # Start cache stats collection task
    agent = get_agent(get_settings())
    cache_stats_task = asyncio.create_task(collect_cache_stats_periodically(agent))

    yield

    # Cancel cache stats task
    cache_stats_task.cancel()

    # ... existing shutdown ...
```

**Estimated Time:** 4 hours
**Risk:** Low - Straightforward metrics collection

---

#### **Phase 6: Testing & Validation (Priority: HIGH)**

**Task 6.1: Unit Tests for Metrics**
```python
# tests/test_metrics.py
import pytest
from app.metrics import (
    http_requests_total,
    agent_completions_total,
    cache_operations_total,
)
from prometheus_client import REGISTRY

def test_http_requests_metric():
    """Test HTTP requests counter."""
    initial = http_requests_total.labels(
        method="GET",
        endpoint="/api/chat",
        status=200,
    )._value.get()

    http_requests_total.labels(
        method="GET",
        endpoint="/api/chat",
        status=200,
    ).inc()

    final = http_requests_total.labels(
        method="GET",
        endpoint="/api/chat",
        status=200,
    )._value.get()

    assert final == initial + 1

def test_metrics_endpoint():
    """Test /metrics endpoint returns OpenMetrics format."""
    from prometheus_client import generate_latest

    metrics_output = generate_latest(REGISTRY).decode("utf-8")

    # Validate format
    assert "# HELP" in metrics_output
    assert "# TYPE" in metrics_output
    assert "http_requests_total" in metrics_output
```

**Task 6.2: Integration Tests**
```python
# tests/test_prometheus_integration.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_metrics_endpoint_exists(client):
    """Test /metrics endpoint is available."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

def test_metrics_track_requests(client):
    """Test metrics track HTTP requests."""
    # Make request
    response = client.post("/api/chat", json={
        "message": "test",
    })

    # Check metrics
    metrics_response = client.get("/metrics")
    metrics_text = metrics_response.text

    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text

@pytest.mark.asyncio
async def test_agent_metrics_collected(tmp_path):
    """Test agent execution metrics are collected."""
    from app.agent.filesystem_agent import create_agent
    from app.metrics import agent_completions_total

    agent = create_agent(
        api_key="test",
        endpoint="https://test.openai.azure.com",
        deployment_name="gpt-4",
        api_version="2024-02-15-preview",
        data_root=tmp_path,
    )

    initial = agent_completions_total.labels(status="success")._value.get()

    # Execute agent (mock LLM call)
    # ... test execution ...

    final = agent_completions_total.labels(status="success")._value.get()
    assert final > initial
```

**Estimated Time:** 5 hours
**Risk:** Low - Standard testing

---

#### **Phase 7: Prometheus Server Setup (Priority: MEDIUM)**

**Task 7.1: Create Prometheus Configuration**
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'filesystem-agent'
    environment: 'production'

scrape_configs:
  - job_name: 'filesystem-agent-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
```

**Task 7.2: Create Docker Compose for Monitoring Stack**
```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: filesystem-agent-prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    ports:
      - '9090:9090'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: filesystem-agent-grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    ports:
      - '3000:3000'
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

**Task 7.3: Start Monitoring Stack**
```bash
# Start Prometheus + Grafana
docker-compose -f docker-compose.monitoring.yml up -d

# Access Prometheus: http://localhost:9090
# Access Grafana: http://localhost:3000 (admin/admin)
```

**Estimated Time:** 2 hours
**Risk:** Low - Standard setup

---

#### **Phase 8: Grafana Dashboards (Priority: MEDIUM)**

**Task 8.1: Create API Performance Dashboard**

Panels:
1. **Request Rate** (Graph)
   - Metric: `rate(http_requests_total[5m])`
   - Group by: endpoint

2. **Latency Percentiles** (Graph)
   - Metric: `histogram_quantile(0.50|0.95|0.99, http_request_duration_seconds_bucket)`

3. **Error Rate** (Graph)
   - Metric: `rate(http_requests_total{status=~"5.."}[5m])`

4. **Active Sessions** (Gauge)
   - Metric: `active_sessions_total`

**Task 8.2: Create Agent Performance Dashboard**

Panels:
1. **Agent Success Rate** (Graph)
   - Metric: `rate(agent_completions_total{status="success"}[5m]) / rate(agent_completions_total[5m])`

2. **Average Iterations** (Graph)
   - Metric: `rate(agent_iterations_total_sum[5m]) / rate(agent_iterations_total_count[5m])`

3. **LLM Call Latency** (Heatmap)
   - Metric: `llm_call_duration_seconds_bucket`

4. **Token Usage Rate** (Graph)
   - Metric: `rate(llm_tokens_total[5m])`
   - Group by: type (input/output)

**Task 8.3: Create Cache Performance Dashboard**

Panels:
1. **Cache Hit Rate** (Graph)
   - Metric: `rate(cache_operations_total{result="hit"}[5m]) / rate(cache_operations_total{operation="get"}[5m])`
   - Group by: cache_type

2. **Cache Size** (Graph)
   - Metric: `cache_size_bytes`
   - Group by: cache_type

3. **Cache Invalidation Rate** (Graph)
   - Metric: `rate(cache_invalidations_total[5m])`
   - Group by: reason

4. **Cache Operation Latency** (Heatmap)
   - Metric: `cache_operation_duration_seconds_bucket`

**Task 8.4: Create System Health Dashboard**

Panels:
1. **Tool Execution Rate** (Graph)
   - Metric: `rate(tool_executions_total[5m])`
   - Group by: tool_name

2. **Tool Success Rate** (Graph)
   - Metric: `rate(tool_executions_total{status="success"}[5m]) / rate(tool_executions_total[5m])`

3. **Sandbox Timeouts** (Graph)
   - Metric: `rate(sandbox_timeouts_total[5m])`

4. **Security Blocks** (Graph)
   - Metric: `rate(sandbox_security_blocks_total[5m])`
   - Group by: block_type

**Task 8.5: Export Dashboard JSON**
```bash
# Export dashboards for version control
mkdir -p grafana/dashboards
# Export from Grafana UI → Share → Export → Save to JSON
```

**Estimated Time:** 6 hours
**Risk:** Low - Dashboard creation

---

#### **Phase 9: Alerting Rules (Priority: LOW)**

**Task 9.1: Create Alert Rules** (`prometheus-alerts.yml`)
```yaml
groups:
  - name: filesystem_agent_alerts
    interval: 30s
    rules:
      # High Error Rate
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} req/s for {{ $labels.endpoint }}"

      # Agent Max Iterations Frequently Reached
      - alert: AgentMaxIterations
        expr: |
          rate(agent_completions_total{status="max_iterations"}[10m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent frequently reaching max iterations"
          description: "{{ $value }} agents reaching max iterations per second"

      # High LLM Latency
      - alert: HighLLMLatency
        expr: |
          histogram_quantile(0.95, llm_call_duration_seconds_bucket) > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High LLM API latency"
          description: "P95 LLM latency is {{ $value }}s"

      # Low Cache Hit Rate
      - alert: LowCacheHitRate
        expr: |
          rate(cache_operations_total{result="hit"}[10m]) /
          rate(cache_operations_total{operation="get"}[10m]) < 0.5
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Cache hit rate below 50%"
          description: "Cache hit rate is {{ $value }}"

      # High Token Usage
      - alert: HighTokenUsage
        expr: |
          rate(llm_tokens_total[1h]) > 100000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High token usage rate"
          description: "Using {{ $value }} tokens/s - check for runaway requests"
```

**Task 9.2: Configure Alertmanager**
```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://your-webhook-url'
        send_resolved: true
    # Or email config:
    # email_configs:
    #   - to: 'alerts@example.com'
    #     from: 'prometheus@example.com'
    #     smarthost: 'smtp.example.com:587'
```

**Estimated Time:** 3 hours
**Risk:** Low - Alert configuration

---

### 5.4 Prometheus Integration Summary

**Total Estimated Time:** 32 hours (~4 days)

**Priority Breakdown:**
- **Phase 1-4:** Critical - Core metrics and instrumentation
- **Phase 5:** Important - Cache metrics
- **Phase 6:** Critical - Testing
- **Phase 7-8:** Important - Monitoring stack and visualization
- **Phase 9:** Nice to have - Alerting

**Expected Benefits:**
- Real-time system performance monitoring
- API performance tracking (latency, error rate)
- Agent execution metrics
- Cache performance visibility
- Long-term trend analysis
- Alerting on anomalies

---

## 6. Kế Hoạch Triển Khai

### 6.1 Phân Chia Pha Theo Ưu Tiên

#### **Phase 1: Foundation (Week 1)**
**Mục tiêu:** Setup infrastructure, configuration, testing framework

**Tasks:**
- [ ] Langfuse Phase 1-2: Setup & Configuration (3 hours)
- [ ] Prometheus Phase 1-2: Dependencies & Metrics Definition (3 hours)
- [ ] Create test environments (dev, staging) (2 hours)
- [ ] Setup CI/CD for testing (2 hours)

**Deliverables:**
- Environment variables configured
- Test accounts created (Langfuse cloud)
- Metrics definitions finalized
- Test suite scaffolding

**Total Time:** 10 hours (~1.5 days)

---

#### **Phase 2: Core Observability (Week 1-2)**
**Mục tiêu:** Implement core tracing and metrics collection

**Tasks:**
- [ ] Langfuse Phase 3: Agent-Level Tracing (8 hours)
- [ ] Prometheus Phase 3: Instrumentation (3 hours)
- [ ] Prometheus Phase 4: Agent & Tool Instrumentation (6 hours)
- [ ] Integration testing (4 hours)

**Deliverables:**
- Agent execution fully traced in Langfuse
- LLM calls tracked with tokens
- Tool execution traced
- HTTP requests tracked in Prometheus
- Agent metrics collected

**Total Time:** 21 hours (~3 days)

---

#### **Phase 3: API & Cache Integration (Week 2)**
**Mục tiêu:** Extend observability to all components

**Tasks:**
- [ ] Langfuse Phase 4: API Route Integration (4 hours)
- [ ] Prometheus Phase 5: Cache Metrics (4 hours)
- [ ] Streaming endpoints instrumentation (3 hours)
- [ ] Document CRUD metrics (2 hours)

**Deliverables:**
- All API endpoints traced
- Streaming responses tracked
- Cache hit/miss metrics
- File operations metrics

**Total Time:** 13 hours (~2 days)

---

#### **Phase 4: Testing & Validation (Week 3)**
**Mục tiêu:** Comprehensive testing and bug fixes

**Tasks:**
- [ ] Langfuse Phase 5: Testing & Validation (6 hours)
- [ ] Prometheus Phase 6: Testing & Validation (5 hours)
- [ ] Load testing with observability (4 hours)
- [ ] Bug fixes and refinements (5 hours)

**Deliverables:**
- Unit tests for all instrumentation
- Integration tests passing
- Load test results with metrics
- Bug fixes completed

**Total Time:** 20 hours (~3 days)

---

#### **Phase 5: Monitoring & Visualization (Week 3-4)**
**Mục tiêu:** Setup monitoring stack and dashboards

**Tasks:**
- [ ] Prometheus Phase 7: Prometheus Server Setup (2 hours)
- [ ] Prometheus Phase 8: Grafana Dashboards (6 hours)
- [ ] Langfuse Phase 6: Dashboard Setup (2 hours)
- [ ] Documentation (4 hours)

**Deliverables:**
- Prometheus + Grafana running
- 4 Grafana dashboards configured
- Langfuse dashboards configured
- Complete documentation

**Total Time:** 14 hours (~2 days)

---

#### **Phase 6: Alerting & Optimization (Week 4)**
**Mục tiêu:** Production readiness

**Tasks:**
- [ ] Prometheus Phase 9: Alerting Rules (3 hours)
- [ ] Performance optimization based on metrics (4 hours)
- [ ] Production deployment checklist (2 hours)
- [ ] Training documentation (3 hours)

**Deliverables:**
- Alert rules configured
- Performance optimizations applied
- Production deployment guide
- Team training materials

**Total Time:** 12 hours (~1.5 days)

---

### 6.2 Timeline Summary

```
Week 1:
├─ Day 1-2: Foundation setup (Langfuse + Prometheus config)
└─ Day 3-5: Core observability (Agent tracing, LLM metrics)

Week 2:
├─ Day 1-2: API integration (Routes + streaming)
└─ Day 3-5: Cache metrics + component instrumentation

Week 3:
├─ Day 1-3: Comprehensive testing
└─ Day 4-5: Monitoring stack setup

Week 4:
├─ Day 1-2: Dashboards and visualization
└─ Day 3-4: Alerting and production prep
```

**Total Time:** ~90 hours (~2 weeks full-time, ~4 weeks part-time)

---

### 6.3 Resource Requirements

#### **Engineering Resources**
- **1 Backend Engineer** (Python/FastAPI expertise)
  - Implement Langfuse integration
  - Implement Prometheus instrumentation
  - Write tests

- **1 DevOps Engineer** (part-time, Week 3-4)
  - Setup Prometheus + Grafana
  - Configure alerts
  - Production deployment

#### **Infrastructure**
- **Langfuse Cloud Account** (Free tier for development)
  - Or self-hosted Langfuse (requires Docker)
- **Prometheus Server** (can run locally via Docker)
- **Grafana** (bundled with Prometheus in Docker Compose)
- **Test Environment** (same infrastructure as production)

#### **Budget Estimate**
- **Langfuse Cloud:** $0-$99/month (depends on trace volume)
- **Infrastructure:** $0 (local Docker) or $20-50/month (cloud VMs)
- **Engineering Time:** 90 hours × $50-150/hour = $4,500-13,500

---

### 6.4 Success Criteria

#### **Functional Requirements**
- [ ] All LLM calls traced in Langfuse với full context
- [ ] Token usage tracked per request
- [ ] Agent iterations visible in traces
- [ ] Tool execution traced with results
- [ ] HTTP requests tracked in Prometheus
- [ ] Cache hit/miss metrics exposed
- [ ] Grafana dashboards operational
- [ ] Alerts configured and testing

#### **Performance Requirements**
- [ ] Observability overhead < 5% latency increase
- [ ] Metrics collection < 1% CPU overhead
- [ ] Trace sampling configurable (support production load)
- [ ] Metrics scraping < 1 second per scrape

#### **Quality Requirements**
- [ ] >80% test coverage for instrumentation code
- [ ] All critical paths instrumented
- [ ] No data leaks (sanitize sensitive data in traces)
- [ ] Documentation complete

---

## 7. Rủi Ro & Giải Pháp

### 7.1 Technical Risks

#### **Risk 1: Performance Overhead from Tracing**
**Likelihood:** Medium
**Impact:** High
**Mitigation:**
- Implement sampling (start with 100%, reduce to 10-20% in production)
- Async trace flushing (non-blocking)
- Batch trace uploads
- Monitor overhead via dedicated metrics

**Contingency:**
- Add feature flag to disable tracing dynamically
- Implement circuit breaker for tracing failures

---

#### **Risk 2: Token Counting Inaccuracy**
**Likelihood:** Low
**Impact:** Medium
**Mitigation:**
- Use Azure OpenAI response usage object (accurate)
- Validate against Azure billing reports weekly
- Add fallback token estimation if usage missing

**Contingency:**
- Use tiktoken library for client-side estimation
- Alert on discrepancies > 10%

---

#### **Risk 3: Langfuse API Rate Limits**
**Likelihood:** Medium (if using cloud)
**Impact:** Medium
**Mitigation:**
- Batch trace uploads (built into SDK)
- Implement exponential backoff on failures
- Monitor Langfuse SDK queue size
- Self-host Langfuse if rate limits hit frequently

**Contingency:**
- Queue traces locally, replay on failure
- Upgrade Langfuse plan or self-host

---

#### **Risk 4: Prometheus Metric Cardinality Explosion**
**Likelihood:** Low
**Impact:** High
**Mitigation:**
- Avoid high-cardinality labels (no session_id in labels)
- Use histogram buckets instead of individual timings
- Monitor Prometheus memory usage
- Set retention policy (30 days default)

**Contingency:**
- Aggregate metrics with recording rules
- Drop low-value metrics
- Scale Prometheus horizontally (federation)

---

### 7.2 Integration Risks

#### **Risk 5: Breaking Changes to Agent Code**
**Likelihood:** Low
**Impact:** High
**Mitigation:**
- Comprehensive test suite before changes
- Feature flags for observability (can disable)
- Code review process
- Gradual rollout (dev → staging → production)

**Contingency:**
- Quick rollback mechanism
- Maintain non-instrumented code path as fallback

---

#### **Risk 6: Langfuse SDK Compatibility Issues**
**Likelihood:** Low
**Impact:** Medium
**Mitigation:**
- Pin SDK versions in pyproject.toml
- Test SDK updates in staging first
- Monitor Langfuse SDK changelog
- Subscribe to breaking change notifications

**Contingency:**
- Maintain wrapper abstraction over Langfuse SDK
- Easy to swap tracing backend if needed

---

### 7.3 Operational Risks

#### **Risk 7: Prometheus Storage Growth**
**Likelihood:** High
**Impact:** Medium
**Mitigation:**
- Set 30-day retention policy
- Monitor disk usage with alerts
- Regular cleanup of old data
- Use Prometheus remote write for long-term storage (optional)

**Contingency:**
- Reduce scrape interval (15s → 60s)
- Archive old data to S3/Azure Blob
- Scale storage volume

---

#### **Risk 8: Alert Fatigue**
**Likelihood:** Medium
**Impact:** Medium
**Mitigation:**
- Start with conservative thresholds
- Tune alerts based on baseline metrics
- Implement alert grouping (max 1 alert per 15 min per rule)
- Regular alert review meetings

**Contingency:**
- Disable noisy alerts temporarily
- Adjust thresholds based on feedback
- Implement alert acknowledgment system

---

### 7.4 Data & Privacy Risks

#### **Risk 9: Sensitive Data in Traces**
**Likelihood:** Medium
**Impact:** High
**Mitigation:**
- Sanitize file paths before tracing (remove user info)
- Truncate file contents in traces (max 1000 chars)
- Redact patterns (emails, API keys) in tool outputs
- Document data retention policies

**Contingency:**
- Add scrubbing layer before Langfuse upload
- Implement data deletion API
- Self-host Langfuse for full control

---

#### **Risk 10: Trace Data Volume Cost**
**Likelihood:** Medium (if high traffic)
**Impact:** Medium
**Mitigation:**
- Implement sampling (10% in production)
- Compress trace payloads
- Monitor Langfuse billing dashboard
- Set budget alerts

**Contingency:**
- Reduce sampling rate further
- Self-host Langfuse (free, but infrastructure cost)
- Switch to lighter tracing solution

---

## 8. Appendix

### 8.1 Key Metrics Quick Reference

| Metric | Type | Purpose | Target |
|--------|------|---------|--------|
| `agent_completions_total{status}` | Counter | Track agent success rate | >95% success |
| `llm_tokens_total{type}` | Counter | Track token usage and cost | Monitor trends |
| `cache_operations_total{result}` | Counter | Track cache effectiveness | >80% hit rate |
| `http_request_duration_seconds` | Histogram | Track API latency | p95 < 5s |
| `tool_executions_total{tool_name, status}` | Counter | Track tool reliability | >95% success |
| `agent_iterations_total` | Histogram | Track agent efficiency | Median < 3 |

### 8.2 Useful Prometheus Queries

```promql
# API Request Rate (requests per second)
rate(http_requests_total[5m])

# API P95 Latency
histogram_quantile(0.95, http_request_duration_seconds_bucket)

# Error Rate Percentage
100 * rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Cache Hit Rate Percentage
100 * rate(cache_operations_total{result="hit"}[5m]) / rate(cache_operations_total{operation="get"}[5m])

# Average Agent Iterations
rate(agent_iterations_total_sum[5m]) / rate(agent_iterations_total_count[5m])

# Token Cost Estimation (assuming $0.03 per 1K tokens)
(rate(llm_tokens_total[1h]) / 1000) * 0.03 * 3600  # Cost per hour

# Tool Execution Success Rate
rate(tool_executions_total{status="success"}[5m]) / rate(tool_executions_total[5m])

# Active Sessions
active_sessions_total
```

### 8.3 Environment Variables Summary

```bash
# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_ENVIRONMENT=production
LANGFUSE_RELEASE=1.0.0
LANGFUSE_SAMPLE_RATE=1.0

# Prometheus
PROMETHEUS_ENABLED=true
PROMETHEUS_METRICS_PATH=/metrics
PROMETHEUS_EXCLUDE_PATHS=/health,/metrics
PROMETHEUS_BUCKETS=0.01,0.05,0.1,0.5,1.0,5.0,10.0
```

### 8.4 Dependencies to Add

```toml
[tool.poetry.dependencies]
# Observability
langfuse = "^2.48.0"
prometheus-client = "^0.20.0"
prometheus-fastapi-instrumentator = "^6.1.0"
```

### 8.5 Useful Commands

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Query Prometheus metrics
curl http://localhost:9090/api/v1/query?query=http_requests_total

# View application metrics
curl http://localhost:8000/metrics

# Test Langfuse connection
poetry run python -c "from langfuse import Langfuse; print(Langfuse().get_trace('test-id'))"

# Run load test with observability
locust -f tests/load_test.py --host http://localhost:8000

# Export Grafana dashboard
curl -u admin:admin http://localhost:3000/api/dashboards/uid/<dashboard-uid> > dashboard.json
```

---

## Tóm Tắt Kết Luận

### Core Business Impact

**Filesystem Agent Showcase** là một demo project cho AI agents pattern mới. Hai điểm quan trọng nhất về core business:

1. **Agent Loop Quality:** Agent phải đạt final answer trong <5 iterations với >95% success rate
2. **Cache Performance:** Cache phải maintain >80% hit rate để justify v3.0 investment

### Integration Strategy

**Langfuse + Prometheus bổ sung cho nhau:**

- **Langfuse:** Deep dive vào LLM reasoning, debug specific requests, cost analysis per session
- **Prometheus:** System health, real-time alerting, long-term trends, operational metrics

### Implementation Priority

**High Priority (Week 1-2):**
1. Langfuse Agent-level tracing (8h)
2. Prometheus instrumentation (9h)
3. Testing (11h)

**Medium Priority (Week 3):**
4. API integration (7h)
5. Monitoring stack (8h)

**Low Priority (Week 4):**
6. Dashboards (6h)
7. Alerting (3h)

### Total Investment

- **Time:** ~90 hours (~4 weeks part-time)
- **Cost:** $0-100/month (Langfuse cloud + infrastructure)
- **ROI:** Visibility into agent behavior, cost control, performance optimization

### Key Success Metrics

1. Agent success rate >95%
2. P95 latency <5s
3. Cache hit rate >80%
4. Token cost tracking accurate within 5%
5. Zero production incidents due to observability overhead

---

**Ngày hoàn thành phân tích:** 2026-01-23
**Người phân tích:** Claude Code với 4 parallel agents
**Trạng thái:** Ready for implementation
