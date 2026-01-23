# Dependency Injection Guide

This guide explains the unified dependency injection system in `app/dependencies.py` (Phase 2.5 implementation).

## Overview

The dependency injection system provides centralized access to all application components:

- **Settings**: Application configuration
- **SessionRepository**: Chat session management
- **ToolRegistry**: Bash tool definitions
- **AgentFactory**: Agent creation with proper DI
- **FilesystemAgent**: Created via factory

## Available Dependencies

### 1. get_settings()

Returns cached Settings singleton.

```python
from app.dependencies import get_settings

settings = get_settings()
print(settings.azure_openai_deployment_name)
```

**FastAPI usage:**
```python
from fastapi import Depends
from app.dependencies import get_settings

@router.get("/config")
def get_config(settings: Settings = Depends(get_settings)):
    return {"model": settings.azure_openai_deployment_name}
```

### 2. get_session_repository()

Returns SessionRepository singleton for managing chat sessions.

```python
from app.dependencies import get_session_repository

repo = get_session_repository()
session = await repo.get_or_create("session-id")
```

**FastAPI usage:**
```python
from fastapi import Depends
from app.dependencies import get_session_repository

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    repo: SessionRepository = Depends(get_session_repository)
):
    session = await repo.get(session_id)
    return {"history": session.get_history()}
```

### 3. get_tool_registry()

Returns ToolRegistry singleton with all bash tools registered.

```python
from app.dependencies import get_tool_registry

registry = get_tool_registry()
print(registry.list_names())  # ['grep', 'find', 'cat', 'head', 'tail', 'ls', 'wc']
```

**Use cases:**
- List available tools
- Get tool definitions
- Build commands dynamically
- Check if tool is cacheable

```python
registry = get_tool_registry()

# Get tool definition
grep_tool = registry.get("grep")
print(grep_tool.description)

# Build command
cmd = registry.build_command("grep", {
    "pattern": "TODO",
    "path": ".",
    "recursive": True
})
```

### 4. get_agent_factory_dependency()

Returns AgentFactory singleton for creating agents.

```python
from app.dependencies import get_agent_factory_dependency

factory = get_agent_factory_dependency()
agent = factory.create_from_settings(settings)
```

**Note:** Usually you don't need to call this directly. Use `get_agent()` instead.

### 5. get_agent()

Creates a new FilesystemAgent instance using the factory.

```python
from app.dependencies import get_agent

# Uses default settings
agent = get_agent()

# Or with custom settings
agent = get_agent(settings=my_settings)
```

**FastAPI usage:**
```python
from fastapi import Depends
from app.dependencies import get_agent

@router.post("/chat")
async def chat(
    message: str,
    agent: FilesystemAgent = Depends(get_agent)
):
    response = await agent.chat(message)
    return {"response": response.message}
```

**Important:** Unlike other dependencies, `get_agent()` creates a **new instance** on each call. This is intentional - agents are stateless and should not be shared across requests.

## Migration from create_agent()

### Old Way (Legacy)

```python
from app.agent.filesystem_agent import create_agent

agent = create_agent(
    api_key=settings.azure_openai_api_key,
    endpoint=settings.azure_openai_endpoint,
    deployment_name=settings.azure_openai_deployment_name,
    api_version=settings.azure_openai_api_version,
    data_root=settings.data_root,
    sandbox_enabled=settings.sandbox_enabled,
    # ... 15+ more parameters
)
```

### New Way (Recommended)

```python
from app.dependencies import get_agent

# All settings automatically configured from environment
agent = get_agent()
```

### Benefits of New Approach

1. **Less boilerplate**: No need to pass 20+ parameters
2. **Better testability**: Easy to mock factory for tests
3. **Centralized configuration**: All settings come from one place
4. **Type safety**: Factory validates configuration
5. **Dependency injection**: Follows SOLID principles

## Testing with Dependencies

### reset_dependencies()

Clears all singleton instances. Use this in test fixtures.

```python
import pytest
from app.dependencies import reset_dependencies

@pytest.fixture(autouse=True)
def reset_deps():
    """Reset dependencies before each test."""
    reset_dependencies()
    yield
    reset_dependencies()
```

### Example Test

```python
from app.dependencies import get_agent, get_settings, reset_dependencies

def test_agent_creation():
    reset_dependencies()

    # Get agent
    agent = get_agent()

    # Verify it works
    assert isinstance(agent, FilesystemAgent)
```

### Mocking Dependencies

```python
from unittest.mock import patch, MagicMock

def test_with_mock_agent():
    mock_agent = MagicMock()

    with patch('app.dependencies.get_agent', return_value=mock_agent):
        # Your test code here
        agent = get_agent()
        assert agent is mock_agent
```

## FastAPI Integration Examples

### Simple Route

```python
from fastapi import APIRouter, Depends
from app.dependencies import get_agent

router = APIRouter()

@router.post("/query")
async def query(
    message: str,
    agent: FilesystemAgent = Depends(get_agent)
):
    response = await agent.chat(message)
    return {"response": response.message}
```

### Multiple Dependencies

```python
@router.post("/chat")
async def chat(
    message: str,
    session_id: str,
    agent: FilesystemAgent = Depends(get_agent),
    repo: SessionRepository = Depends(get_session_repository),
    settings: Settings = Depends(get_settings)
):
    # All dependencies injected automatically
    session = await repo.get_or_create(session_id)
    response = await agent.chat(message, history=session.get_history())

    session.add_message("user", message)
    session.add_message("assistant", response.message)
    await repo.update(session_id, session)

    return {
        "response": response.message,
        "model": settings.azure_openai_deployment_name
    }
```

### Custom Settings Override

```python
@router.post("/chat-with-model")
async def chat_with_model(
    message: str,
    model: str,
    settings: Settings = Depends(get_settings)
):
    # Override settings for specific model
    custom_settings = settings.copy()
    custom_settings.azure_openai_deployment_name = model

    # Create agent with custom settings
    agent = get_agent(settings=custom_settings)

    response = await agent.chat(message)
    return {"response": response.message}
```

## Singleton vs Per-Request

| Dependency | Lifecycle | Reason |
|------------|-----------|--------|
| `get_settings()` | Singleton | Configuration doesn't change |
| `get_session_repository()` | Singleton | Shared state across requests |
| `get_tool_registry()` | Singleton | Tool definitions are static |
| `get_agent_factory_dependency()` | Singleton | Factory is stateless |
| `get_agent()` | Per-request | Creates new instance each time |

## Architecture

```
FastAPI Route
    ↓
get_agent(settings?) → get_agent_factory_dependency()
    ↓                           ↓
AgentFactory.create_from_settings()
    ↓
ComponentFactory creates:
    - AzureOpenAI client
    - SandboxExecutor
    - CacheManager
    - ParallelToolOrchestrator
    ↓
FilesystemAgent (fully configured)
```

## Best Practices

1. **Always use dependencies in routes**: Don't create agents manually
2. **Use reset_dependencies() in tests**: Ensures clean state
3. **Don't share agents**: Create new agent for each request
4. **Mock at dependency level**: Mock `get_agent()`, not internal components
5. **Use type hints**: FastAPI validates dependency types

## Backward Compatibility

The old `create_agent()` function still works but is now considered legacy:

```python
# Still works (backward compatible)
from app.agent.filesystem_agent import create_agent
agent = create_agent(...)

# But prefer this (new approach)
from app.dependencies import get_agent
agent = get_agent()
```

Existing code will continue to work, but new code should use the dependency injection system.

## Complete Example

```python
from fastapi import FastAPI, Depends, HTTPException
from app.dependencies import (
    get_agent,
    get_session_repository,
    get_settings,
)
from app.agent.filesystem_agent import FilesystemAgent
from app.repositories.session_repository import SessionRepository
from app.settings import Settings

app = FastAPI()

@app.post("/api/chat")
async def chat_endpoint(
    message: str,
    session_id: str,
    agent: FilesystemAgent = Depends(get_agent),
    repo: SessionRepository = Depends(get_session_repository),
    settings: Settings = Depends(get_settings),
):
    """Complete chat endpoint with all dependencies."""
    try:
        # Get or create session
        session = await repo.get_or_create(session_id)

        # Get chat response
        response = await agent.chat(
            user_message=message,
            history=session.get_history()
        )

        # Update session
        session.add_message("user", message)
        session.add_message("assistant", response.message)
        await repo.update(session_id, session)

        return {
            "response": response.message,
            "session_id": session_id,
            "model": settings.azure_openai_deployment_name,
            "tool_calls": len(response.tool_calls),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## See Also

- [examples/dependency_injection_demo.py](../examples/dependency_injection_demo.py) - Working examples
- [app/dependencies.py](../app/dependencies.py) - Implementation
- [tests/test_dependencies.py](../tests/test_dependencies.py) - Test examples
