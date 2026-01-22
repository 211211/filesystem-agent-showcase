# Repository Guidelines

## Project Structure & Module Organization
- `app/`: FastAPI app and agent implementation. Key areas: `app/agent/` (LLM loop, tools, prompts), `app/api/` (HTTP routes), `app/sandbox/` (command execution), `app/cache/` (cache systems), `app/main.py` (ASGI entry), `app/cli.py` (CLI).
- `tests/`: pytest suite.
- `data/`: example documents the agent explores (projects, knowledge-base, notes, benchmark).
- `docs/`, `examples/`, `scripts/`: docs, runnable examples, and helper scripts.
- `tmp/`: cache storage (default).

## Build, Test, and Development Commands
- `make install` / `poetry install`: install dependencies.
- `make dev` or `poetry run uvicorn app.main:app --reload`: run the API locally.
- `make test`: run pytest.
- `make test-cov`: run pytest with coverage.
- `make lint`: ruff linting.
- `make format`: ruff formatting and auto-fix.
- `make container` / `make container-dev`: build and run with Docker or Podman.

## Coding Style & Naming Conventions
- Python 3.11, 4-space indentation, line length 100 (ruff).
- Use `snake_case` for modules/functions, `CapWords` for classes, `UPPER_SNAKE` for constants.
- Keep async I/O in agent and API layers; prefer type hints for public functions.

## Testing Guidelines
- pytest + pytest-asyncio; tests live in `tests/` with `test_*.py` and `test_*` functions.
- Run a single test: `poetry run pytest tests/test_agent.py::test_name`.
- Add or adjust tests when changing tool behavior, caching, or streaming endpoints.

## Commit & Pull Request Guidelines
- Recent history uses conventional-style prefixes (e.g., `feat:`); keep messages short and imperative.
- PRs should include a clear summary, test results, and linked issues; update docs when API behavior changes.

## Configuration & Security Tips
- Copy `.env.example` to `.env` for Azure OpenAI settings; do not commit secrets.
- Data root defaults to `./data` (see `app/config.py`); tool allowlist lives in `app/agent/tools/bash_tools.py`.
- Sandbox limits file size and output size; adjust via environment variables if needed.
