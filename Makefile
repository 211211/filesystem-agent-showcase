# Filesystem Agent Showcase - Makefile
# Convenient commands for development and deployment

.PHONY: help install dev test lint format container container-dev clean

# Auto-detect container runtime (prefer podman over docker)
CONTAINER_ENGINE := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
CONTAINER_NAME := $(notdir $(CONTAINER_ENGINE))

# Compose command detection
ifeq ($(CONTAINER_NAME),podman)
    COMPOSE_CMD := $(shell command -v podman-compose 2>/dev/null || echo "podman compose")
else
    COMPOSE_CMD := docker compose
endif

# Default target
help:
	@echo "Filesystem Agent Showcase"
	@echo ""
	@echo "Container runtime: $(CONTAINER_NAME)"
	@echo "Compose command: $(COMPOSE_CMD)"
	@echo ""
	@echo "Usage:"
	@echo "  make install        Install dependencies with Poetry"
	@echo "  make dev            Run development server with hot reload"
	@echo "  make test           Run tests with pytest"
	@echo "  make test-cov       Run tests with coverage report"
	@echo "  make lint           Run linting with ruff"
	@echo "  make format         Format code with ruff"
	@echo ""
	@echo "Container commands (works with Docker or Podman):"
	@echo "  make container      Build and run container"
	@echo "  make container-dev  Run container in development mode"
	@echo "  make container-build Build container image"
	@echo "  make container-stop Stop containers"
	@echo "  make container-logs View container logs"
	@echo ""
	@echo "  make clean          Clean up temporary files"
	@echo ""

# Install dependencies
install:
	poetry install

# Run development server
dev:
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	poetry run pytest tests/ -v

# Run tests with coverage
test-cov:
	poetry run pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# Run linting
lint:
	poetry run ruff check app/ tests/

# Format code
format:
	poetry run ruff format app/ tests/
	poetry run ruff check --fix app/ tests/

# Build container image
container-build:
	$(CONTAINER_ENGINE) build -t filesystem-agent-showcase .

# Run with container
container: container-build
	$(COMPOSE_CMD) up filesystem-agent

# Run container in development mode
container-dev:
	$(COMPOSE_CMD) --profile dev up filesystem-agent-dev

# Stop containers
container-stop:
	$(COMPOSE_CMD) down

# View container logs
container-logs:
	$(COMPOSE_CMD) logs -f

# Legacy docker aliases (for backwards compatibility)
docker: container
docker-build: container-build
docker-dev: container-dev
docker-stop: container-stop

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# Quick start for first-time setup
setup: install
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "1. Copy .env.example to .env and add your Azure OpenAI credentials"
	@echo "2. Run 'make dev' to start the development server"
	@echo "3. Visit http://localhost:8000/docs for API documentation"
	@echo ""
	@echo "For containerized deployment, use 'make container'"
