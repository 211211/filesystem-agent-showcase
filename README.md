# Filesystem Agent Showcase

A demonstration of building AI agents that leverage filesystem and bash tools for document exploration and analysis. Inspired by [Vercel's approach to agentic AI](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash).

## Overview

This project showcases a simple yet powerful pattern for building AI agents: instead of complex vector databases and RAG pipelines, we give the LLM access to familiar filesystem tools like `grep`, `find`, `cat`, and `ls`. The agent can then explore and analyze documents just like a developer would.

### Key Features

- **Simple but Powerful**: No vector database or complex RAG pipeline needed
- **Transparent & Debuggable**: Every tool call is visible and reproducible
- **Secure**: Sandboxed execution with whitelisted commands
- **Extensible**: Easy to add new tools
- **Production-Ready**: FastAPI backend with proper error handling
- **Parallel Execution** (v2.0): Concurrent tool execution for improved performance
- **Adaptive File Reading** (v2.0): Smart strategy selection based on file size
- **Result Caching** (v2.0): TTL-based caching to avoid redundant operations
- **SSE Streaming** (v2.0): Real-time file streaming and search results via Server-Sent Events

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     FastAPI Server                        │
├──────────────────────────────────────────────────────────┤
│  /api/chat        │  /api/documents   │  /api/stream      │
│  - Chat with AI   │  - List documents │  - SSE streaming  │
│  - Tool execution │  - Read/write     │  - File content   │
│  - Parallel tools │  - Delete         │  - Search results │
└────────┬──────────┴───────────────────┴───────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│                   Filesystem Agent                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │  Azure      │  │  Bash Tools │  │  Sandbox    │       │
│  │  OpenAI     │◄►│  grep,find  │◄►│  Executor   │       │
│  │  (GPT-4)    │  │  cat,ls,... │  │  (secure)   │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└──────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│                    Data Directory                         │
│  ├── projects/                                            │
│  │   ├── project-alpha/                                   │
│  │   └── project-beta/                                    │
│  ├── knowledge-base/                                      │
│  │   ├── policies/                                        │
│  │   ├── procedures/                                      │
│  │   └── faqs/                                            │
│  └── notes/                                               │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (for dependency management)
- Azure OpenAI API access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/211211/filesystem-agent-showcase.git
   cd filesystem-agent-showcase
   ```

2. **Install dependencies**
   ```bash
   make install
   # or
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure OpenAI credentials
   ```

4. **Run the server**
   ```bash
   make dev
   # or
   poetry run uvicorn app.main:app --reload
   ```

5. **Open the API docs**

   Navigate to http://localhost:8000/docs

## Usage

### Chat with the Agent

Send a message to the agent and it will use filesystem tools to find answers:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What files are in the projects folder?"}'
```

Response:
```json
{
  "response": "I found 2 project directories in the projects folder:\n\n1. **project-alpha** - A task management web application...\n2. **project-beta** - An AI-powered data analytics platform...",
  "session_id": "abc123",
  "tool_calls": [
    {
      "id": "call_1",
      "name": "ls",
      "arguments": {"path": "projects"}
    }
  ],
  "tool_results": [...]
}
```

### Example Queries

Try these queries to see the agent in action:

- "What files are in the knowledge-base folder?"
- "Find all markdown files that mention authentication"
- "Search for TODO comments in the projects"
- "Summarize the README in project-alpha"
- "What are the security policies?"
- "Compare the tech stacks of both projects"

### Testing Parallel Execution (v2.0)

The parallel execution feature shines when the agent needs to perform multiple operations. Try these queries that trigger parallel tool calls:

**Multi-file search (triggers parallel grep):**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Search for the word learning in all files under benchmark folder, also find all JSON files"}'
```

**Compare multiple files (triggers parallel cat/read):**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Compare the contents of report.md files in benchmark/arxiv-100-papers and benchmark/arxiv-1000-papers"}'
```

**Directory exploration (triggers parallel ls/find):**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "List all directories under benchmark and count files in each"}'
```

### Streaming Endpoints (v2.0)

Stream file content in real-time using Server-Sent Events (SSE):

**Stream file content:**
```bash
curl -N http://localhost:8000/api/stream/file/benchmark/report.md
```

**Stream with grep (search while streaming):**
```bash
curl -N "http://localhost:8000/api/stream/file/benchmark/arxiv-100-papers/metadata.jsonl?query=learning"
```

**Stream search results:**
```bash
curl -N "http://localhost:8000/api/stream/search/benchmark/arxiv-100-papers/metadata.jsonl?pattern=model&max_matches=10"
```

**SSE Event Format:**
```
event: progress
data: {"percent": 25, "bytes_read": 1024}

event: chunk
data: {"content": "file content here..."}

event: match
data: {"line_number": 5, "line_content": "...", "match_start": 10, "match_end": 15}

event: done
data: {"total_bytes": 4096}
```

### Document Management

List documents:
```bash
curl http://localhost:8000/api/documents
```

Read a document:
```bash
curl http://localhost:8000/api/documents/projects/project-alpha/README.md
```

Upload a document:
```bash
curl -X POST http://localhost:8000/api/documents \
  -H "Content-Type: application/json" \
  -d '{"path": "notes/new-note.md", "content": "# My Note\n\nContent here..."}'
```

## Available Tools

The agent has access to these bash tools (all POSIX-compliant for cross-platform compatibility):

| Tool | Description | Example |
|------|-------------|---------|
| `grep` | Search for patterns in files | Find all TODOs |
| `find` | Find files by name pattern | Locate all .md files |
| `cat` | Read file contents | Display README |
| `head` | Read first N lines | Preview large files |
| `ls` | List directory contents | See folder structure |
| `tree` | List files recursively (uses `find`) | Understand organization |
| `wc` | Count lines/words | Get file statistics |

## Platform Compatibility

This project is designed to work on **any Unix-based system**:

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | ✅ Fully supported | Tested on macOS 12+ |
| **Linux** | ✅ Fully supported | Debian, Ubuntu, Fedora, etc. |
| **Windows WSL** | ✅ Supported | Use WSL2 with Ubuntu |

All tools used are **POSIX-compliant** and available by default:
- No additional system packages required
- Works with both BSD (macOS) and GNU (Linux) coreutils
- Container images use `python:3.11-slim` which includes all required tools

## New Features (v2.0)

### Parallel Tool Execution

The agent can now execute multiple tool calls concurrently using asyncio, significantly improving performance when the LLM requests multiple operations.

**How it works:**
- Read-only tools (`grep`, `find`, `cat`, `ls`, `head`, `tail`, `wc`, `tree`) are safe for parallel execution
- Concurrency is controlled by a semaphore (default: 5 concurrent operations)
- Results are automatically reordered to match the original request order
- Falls back to sequential execution for single tools or unknown commands

**Configuration:**
```env
PARALLEL_EXECUTION=true      # Enable/disable parallel execution
MAX_CONCURRENT_TOOLS=5       # Maximum concurrent tool executions
```

### Adaptive File Reading

The agent now intelligently selects the best file reading strategy based on file size, avoiding memory issues with large files while maintaining full content access for smaller ones.

**Strategies:**
| File Size | Strategy | Description |
|-----------|----------|-------------|
| Small (< 1MB) | `full_read` | Read entire file with `cat` |
| Medium (1-100MB) with query | `grep` | Search with `grep -n -m 100` |
| Medium (1-100MB) without query | `head_tail` | Read first + last 100 lines |
| Large (> 100MB) | `head_tail` | Read first + last 100 lines with gap indicator |

**Configuration:**
```env
SMALL_FILE_THRESHOLD=1048576      # 1MB - files below this are read entirely
MEDIUM_FILE_THRESHOLD=104857600   # 100MB - files below this use grep with query
```

### Result Caching

Tool execution results are now cached to avoid redundant operations, improving response times for repeated queries.

**Features:**
- TTL-based expiration (default: 5 minutes)
- LRU eviction when max size is reached
- Path-based invalidation (clear cache entries for modified files)
- Thread-safe operations
- Cache statistics tracking (hits, misses, hit rate)

**Configuration:**
```env
CACHE_ENABLED=true    # Enable/disable caching
CACHE_TTL=300         # Cache entry lifetime in seconds (5 minutes)
CACHE_MAX_SIZE=100    # Maximum number of cached entries
```

### Running Benchmarks

The project includes a benchmark suite to measure v2.0 performance improvements:

```bash
# Run full benchmark (5 iterations)
poetry run python benchmarks/benchmark_v2.py

# Quick benchmark (3 iterations)
poetry run python benchmarks/benchmark_v2.py --quick

# Custom iterations
poetry run python benchmarks/benchmark_v2.py --iterations 10
```

**Benchmark Results (typical):**

| Benchmark | Sequential | Parallel | Speedup |
|-----------|------------|----------|---------|
| 5 tool calls | ~880ms | ~300ms | **2.9x** |
| 10 grep operations | ~2900ms | ~400ms | **7x** |
| Cache hit vs miss | ~290ms | ~0.01ms | **50,000x** |
| Streaming vs cat | ~4.6ms | ~0.3ms | **14x** |

**Benchmark Data:**

The `data/benchmark/` directory contains test files for benchmarking:
```
data/benchmark/
├── arxiv-100-papers/      # 100 paper metadata (JSON)
│   ├── metadata.jsonl     # Paper metadata
│   └── question_and_answers.json
├── arxiv-1000-papers/     # 1000 paper metadata (JSON)
├── report.md              # Sample report
├── results.json           # Benchmark results
└── statistics.json        # Statistics data
```

### SSE Streaming Endpoints

New streaming endpoints provide real-time file content and search results via Server-Sent Events:

**Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `GET /api/stream/file/{path}` | Stream file content in chunks |
| `GET /api/stream/file/{path}?query=pattern` | Stream grep results while reading |
| `GET /api/stream/search/{path}?pattern=regex` | Stream search matches as found |

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `query` | - | Search pattern for grep mode (stream/file only) |
| `pattern` | (required) | Regex pattern for search endpoint |
| `chunk_size` | 8192 | Chunk size in bytes (1KB-1MB) |
| `max_matches` | 100 | Maximum matches to return (1-1000) |

**Use Cases:**
- Progress indication for large file operations
- Real-time search result display
- Memory-efficient large file processing
- Live log file monitoring

## Configuration

All settings can be configured via environment variables in `.env`. Copy `.env.example` to `.env` and update the values.

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| **Azure OpenAI** | | |
| `AZURE_OPENAI_API_KEY` | (required) | Your Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | (required) | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | `gpt-4o` | Model deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-02-15-preview` | API version |
| **Data & Sandbox** | | |
| `DATA_ROOT_PATH` | `./data` | Root directory for file operations |
| `SANDBOX_ENABLED` | `true` | Enable sandbox security |
| `COMMAND_TIMEOUT` | `30` | Command timeout in seconds |
| `MAX_FILE_SIZE` | `10485760` | Max file size for cat (10MB) |
| `MAX_OUTPUT_SIZE` | `1048576` | Max command output size (1MB) |
| **Parallel Execution** | | |
| `PARALLEL_EXECUTION` | `true` | Enable parallel tool execution |
| `MAX_CONCURRENT_TOOLS` | `5` | Max concurrent executions |
| **Caching** | | |
| `CACHE_ENABLED` | `true` | Enable result caching |
| `CACHE_TTL` | `300` | Cache TTL in seconds (5 min) |
| `CACHE_MAX_SIZE` | `100` | Max cached entries |
| **Adaptive Reading** | | |
| `SMALL_FILE_THRESHOLD` | `1048576` | Small file threshold (1MB) |
| `MEDIUM_FILE_THRESHOLD` | `104857600` | Medium file threshold (100MB) |
| **Server** | | |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Enable debug mode |

### Example `.env` File

```env
# Azure OpenAI (required)
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Data & Sandbox
DATA_ROOT_PATH=./data
SANDBOX_ENABLED=true
COMMAND_TIMEOUT=30
MAX_FILE_SIZE=10485760
MAX_OUTPUT_SIZE=1048576

# Parallel Execution (v2.0)
PARALLEL_EXECUTION=true
MAX_CONCURRENT_TOOLS=5

# Caching (v2.0)
CACHE_ENABLED=true
CACHE_TTL=300
CACHE_MAX_SIZE=100

# Adaptive File Reading (v2.0)
SMALL_FILE_THRESHOLD=1048576
MEDIUM_FILE_THRESHOLD=104857600

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

## Security

The sandbox executor provides multiple layers of protection:

1. **Command Whitelist**: Only specific commands are allowed (`grep`, `find`, `cat`, `head`, `tail`, `ls`, `wc`)
2. **Path Confinement**: Operations are restricted to the data directory
3. **Path Traversal Prevention**: `../` patterns are blocked
4. **Execution Timeout**: Commands are killed after configurable timeout (default: 30s)
5. **Output Limits**: Command output truncated at `MAX_OUTPUT_SIZE` (default: 1MB)
6. **File Size Limits**: `cat` operations blocked for files exceeding `MAX_FILE_SIZE` (default: 10MB)

## Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov
```

## Container Deployment (Docker / Podman)

The project supports both **Docker** and **Podman**. The Makefile auto-detects which container runtime is available (prefers Podman if both are installed).

```bash
# Check detected container runtime and available commands
make help

# Build and run container
make container

# Run in background (detached)
make container-up

# Development mode with hot reload
make container-dev

# Stop containers
make container-stop

# View logs
make container-logs

# Open shell in running container
make container-shell

# Clean up container images
make container-clean
```

### Using Podman (Recommended)

Podman is a daemonless, rootless container engine that's fully compatible with Docker.

1. **Install Podman** (if not already installed):
   ```bash
   # macOS
   brew install podman podman-compose

   # Initialize and start Podman machine (macOS/Windows only)
   make podman-init
   make podman-start

   # Or manually:
   podman machine init --cpus 2 --memory 2048
   podman machine start

   # Fedora/RHEL
   sudo dnf install podman podman-compose

   # Ubuntu/Debian
   sudo apt install podman podman-compose
   ```

2. **Check Podman status**:
   ```bash
   make podman-status
   ```

3. **Run with Podman**:
   ```bash
   # The Makefile will automatically use podman if available
   make container

   # Or run directly with podman-compose
   podman-compose up

   # Or with podman compose (built-in)
   podman compose up
   ```

### Using Docker

```bash
# Build and run with Docker
docker compose up

# Or build manually first
docker build -t filesystem-agent-showcase .
docker compose up
```

### Compose File

The project uses `compose.yml` which works with both Podman Compose and Docker Compose. Features include:

- **Production service** (`filesystem-agent`): Optimized for production with read-only data mount
- **Development service** (`filesystem-agent-dev`): Hot reload enabled, use with `--profile dev`
- **Security**: `no-new-privileges` security option, non-root user
- **Resource limits**: 512MB memory limit, 256MB reservation
- **Health checks**: Automatic container health monitoring
- **SELinux support**: `:Z` volume labels for SELinux compatibility

## Project Structure

```
filesystem-agent-showcase/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration with all settings
│   ├── api/
│   │   └── routes/
│   │       ├── chat.py         # Chat endpoint
│   │       ├── documents.py    # Document management
│   │       └── stream.py       # SSE streaming endpoints (v2.0)
│   ├── agent/
│   │   ├── filesystem_agent.py # Core agent logic
│   │   ├── orchestrator.py     # Parallel tool execution (v2.0)
│   │   ├── cache.py            # TTL-based result cache (v2.0)
│   │   ├── prompts.py          # System prompts
│   │   └── tools/
│   │       ├── bash_tools.py   # Tool definitions
│   │       ├── file_tools.py   # File operations
│   │       ├── streaming.py    # Async streaming reader (v2.0)
│   │       └── adaptive_reader.py  # Smart file reading (v2.0)
│   └── sandbox/
│       ├── executor.py         # Secure command execution
│       └── cached_executor.py  # Executor with caching (v2.0)
├── benchmarks/                 # Performance benchmarks (v2.0)
│   └── benchmark_v2.py         # Benchmark suite for v2.0 features
├── data/                       # Sample documents
│   ├── benchmark/              # Benchmark test data
│   ├── knowledge-base/         # Sample knowledge base
│   ├── notes/                  # Sample notes
│   └── projects/               # Sample projects
├── docs/                       # Documentation
│   ├── ANALYSIS_VI.md          # Architecture analysis (Vietnamese)
│   ├── IMPLEMENTATION_PLAN_VI.md   # Implementation plan (Vietnamese)
│   └── CACHE_IMPROVEMENT_PLAN_VI.md # Cache improvement plan (Vietnamese)
├── tests/
│   ├── test_agent.py           # Agent tests
│   ├── test_sandbox.py         # Sandbox tests
│   ├── test_tools.py           # Tool tests
│   ├── test_orchestrator.py    # Parallel execution tests (v2.0)
│   ├── test_cache.py           # Caching tests (v2.0)
│   ├── test_cached_executor.py # Cached executor tests (v2.0)
│   ├── test_streaming.py       # Streaming reader tests (v2.0)
│   ├── test_adaptive_reader.py # Adaptive reader tests (v2.0)
│   ├── test_stream.py          # SSE streaming tests (v2.0)
│   └── test_integration.py     # End-to-end integration tests (v2.0)
├── Dockerfile
├── compose.yml                 # Podman/Docker Compose config
├── Makefile
├── .env.example                # Environment variable template
└── pyproject.toml
```

## Why This Approach?

Traditional RAG systems require:
- Vector databases
- Embedding pipelines
- Chunk management
- Similarity search tuning

This approach offers:
- **Simplicity**: Just give the LLM the tools it needs
- **Precision**: `grep` finds exact matches, no "semantic similarity" issues
- **Debuggability**: You can run the same commands manually
- **Flexibility**: Easy to add new tools or modify behavior

## References

- [Vercel Blog: How to Build Agents with Filesystems and Bash](https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Azure OpenAI Service](https://azure.microsoft.com/en-us/products/ai-services/openai-service)

## License

MIT License - see LICENSE file for details.
