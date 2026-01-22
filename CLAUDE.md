# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Filesystem Agent Showcase is a Python FastAPI application demonstrating AI agents that use filesystem/bash tools instead of traditional RAG pipelines. The LLM (Azure OpenAI) decides which bash commands to execute, and results are fed back in an agentic loop.

Inspired by [Vercel's approach to agentic AI](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash).

## Commands

```bash
# Development
make install          # Install dependencies with Poetry
make dev              # Run dev server with hot reload (localhost:8000)
make test             # Run all tests
make test-cov         # Run tests with coverage report
make lint             # Run ruff linting
make format           # Format code with ruff

# Run a single test
poetry run pytest tests/test_agent.py -v
poetry run pytest tests/test_agent.py::test_function_name -v

# Container (auto-detects Podman or Docker)
make container        # Build and run container
make container-dev    # Development mode with hot reload
make container-stop   # Stop containers

# Benchmarks
poetry run python benchmarks/benchmark_v2.py --quick
```

## Architecture

### Core Agent Loop (app/agent/filesystem_agent.py)

The `FilesystemAgent.chat()` method implements the agentic loop:
1. User message → LLM with tool definitions
2. LLM returns tool calls (function calling)
3. Execute tools via `SandboxExecutor`
4. Feed results back to LLM
5. Repeat until LLM returns final response (max 10 iterations)

```
User Message → FilesystemAgent.chat() → Azure OpenAI (with BASH_TOOLS)
                     ↓                            ↓
              [tool_calls]  ←──────────── LLM Response
                     ↓
         ParallelToolOrchestrator.execute_with_strategy()
                     ↓
         SandboxExecutor.execute() → subprocess (grep/find/cat/ls/...)
                     ↓
              [results] → back to LLM → final response
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `FilesystemAgent` | `app/agent/filesystem_agent.py` | Core agent with chat() and chat_stream() methods |
| `SandboxExecutor` | `app/sandbox/executor.py` | Secure command execution with whitelist |
| `CachedSandboxExecutor` | `app/sandbox/cached_executor.py` | Executor with TTL-based result caching |
| `ParallelToolOrchestrator` | `app/agent/orchestrator.py` | Concurrent tool execution |
| `BASH_TOOLS` | `app/agent/tools/bash_tools.py` | OpenAI tool definitions (JSON schemas) |
| `Settings` | `app/config.py` | Pydantic settings from environment |

### Security Model (SandboxExecutor)

- **Whitelisted commands only**: `grep`, `find`, `cat`, `head`, `tail`, `ls`, `wc`
- **Path confinement**: All paths resolved within `DATA_ROOT_PATH`
- **Path traversal prevention**: `../` patterns blocked
- **Timeout protection**: Commands killed after `COMMAND_TIMEOUT` seconds
- **Size limits**: `MAX_FILE_SIZE` for cat, `MAX_OUTPUT_SIZE` for all output

### API Routes

| Route | Handler | Purpose |
|-------|---------|---------|
| `POST /api/chat` | `app/api/routes/chat.py` | Send message, get response with tool calls |
| `GET /api/stream/file/{path}` | `app/api/routes/stream.py` | SSE streaming file content |
| `GET /api/documents` | `app/api/routes/documents.py` | List/read/write documents |

### Configuration

All via environment variables (see `.env.example`). Key settings in `app/config.py`:

- `AZURE_OPENAI_*`: API credentials (required)
- `PARALLEL_EXECUTION`: Enable concurrent tool execution (default: true)
- `CACHE_ENABLED`: Enable result caching (default: true)
- `SANDBOX_ENABLED`: Enable security checks (default: true)

## Testing

Uses pytest with `asyncio_mode = "auto"`. Test files mirror the app structure:

```bash
# All tests
make test

# Specific test file
poetry run pytest tests/test_sandbox.py -v

# Specific test
poetry run pytest tests/test_agent.py::test_chat_returns_response -v

# With coverage
make test-cov
```

## Adding New Tools

1. Add tool definition to `BASH_TOOLS` in `app/agent/tools/bash_tools.py` (OpenAI function calling format)
2. Add command to `ALLOWED_COMMANDS` in `app/sandbox/executor.py`
3. Implement `build_command()` case in `bash_tools.py`
4. Add tests in `tests/test_tools.py`
