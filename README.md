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

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     FastAPI Server                        │
├──────────────────────────────────────────────────────────┤
│  /api/chat        │  /api/documents                       │
│  - Chat with AI   │  - List documents                     │
│  - Tool execution │  - Read/write/delete                  │
└────────┬──────────┴───────────────────────────────────────┘
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

## Configuration

All settings can be configured via environment variables in `.env`:

```env
# Azure OpenAI (required)
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Data & Sandbox
DATA_ROOT_PATH=./data
SANDBOX_ENABLED=true
COMMAND_TIMEOUT=30          # seconds
MAX_FILE_SIZE=10485760      # 10MB - max file size for cat/read operations
MAX_OUTPUT_SIZE=1048576     # 1MB - max command output size

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
# Check detected container runtime
make help

# Build and run
make container
# or use legacy alias
make docker

# Development mode with hot reload
make container-dev

# Stop containers
make container-stop

# View logs
make container-logs
```

### Using Podman

Podman is a daemonless container engine that's fully compatible with Docker. To use Podman:

1. **Install Podman** (if not already installed):
   ```bash
   # macOS
   brew install podman
   podman machine init
   podman machine start

   # Fedora/RHEL
   sudo dnf install podman podman-compose

   # Ubuntu/Debian
   sudo apt install podman podman-compose
   ```

2. **Run with Podman**:
   ```bash
   # The Makefile will automatically use podman if available
   make container

   # Or run directly
   podman build -t filesystem-agent-showcase .
   podman-compose up
   ```

### Using Docker

```bash
# Build and run with Docker
docker build -t filesystem-agent-showcase .
docker compose up
```

## Project Structure

```
filesystem-agent-showcase/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration
│   ├── api/
│   │   └── routes/
│   │       ├── chat.py         # Chat endpoint
│   │       └── documents.py    # Document management
│   ├── agent/
│   │   ├── filesystem_agent.py # Core agent logic
│   │   ├── prompts.py          # System prompts
│   │   └── tools/
│   │       ├── bash_tools.py   # Tool definitions
│   │       └── file_tools.py   # File operations
│   └── sandbox/
│       └── executor.py         # Secure command execution
├── data/                       # Sample documents
├── tests/                      # Test suite
├── Dockerfile
├── docker-compose.yml
├── Makefile
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
