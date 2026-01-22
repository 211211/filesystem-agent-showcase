# Filesystem Agent Showcase - Makefile
# Convenient commands for development and deployment

.PHONY: help install dev test lint format container container-dev clean

# Auto-detect container runtime (prefer podman over docker)
CONTAINER_ENGINE := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)
CONTAINER_NAME := $(notdir $(CONTAINER_ENGINE))

# Compose command detection with fallback chain
# Priority: podman-compose > podman compose > docker compose > docker-compose
ifeq ($(CONTAINER_NAME),podman)
    ifneq ($(shell command -v podman-compose 2>/dev/null),)
        COMPOSE_CMD := podman-compose
    else
        COMPOSE_CMD := podman compose
    endif
else
    ifneq ($(shell command -v docker 2>/dev/null),)
        COMPOSE_CMD := docker compose
    else
        COMPOSE_CMD := docker-compose
    endif
endif

# Compose file (use compose.yml - works with both Podman and Docker)
COMPOSE_FILE := compose.yml

# Image name
IMAGE_NAME := filesystem-agent-showcase

# Default target
help:
	@echo "Filesystem Agent Showcase"
	@echo ""
	@echo "Container runtime: $(CONTAINER_NAME)"
	@echo "Compose command:   $(COMPOSE_CMD)"
	@echo "Compose file:      $(COMPOSE_FILE)"
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
	@echo "  make container-shell Open shell in running container"
	@echo "  make container-clean Remove container images"
	@echo ""
	@echo "Podman-specific commands:"
	@echo "  make podman-init    Initialize Podman machine (macOS)"
	@echo "  make podman-start   Start Podman machine (macOS)"
	@echo "  make podman-status  Check Podman status"
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
	$(CONTAINER_ENGINE) build -t $(IMAGE_NAME):latest .

# Run with container (production mode)
container: container-build
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) up filesystem-agent

# Run container in background (detached)
container-up: container-build
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) up -d filesystem-agent

# Run container in development mode with hot reload
container-dev:
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) --profile dev up filesystem-agent-dev

# Stop containers
container-stop:
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) down

# View container logs
container-logs:
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) logs -f

# Open shell in running container
container-shell:
	$(CONTAINER_ENGINE) exec -it filesystem-agent-showcase /bin/sh

# Remove container images
container-clean:
	$(CONTAINER_ENGINE) rmi $(IMAGE_NAME):latest $(IMAGE_NAME):dev 2>/dev/null || true
	$(COMPOSE_CMD) -f $(COMPOSE_FILE) down --rmi local 2>/dev/null || true

# Podman-specific: Initialize machine (macOS/Windows)
podman-init:
	@if [ "$(CONTAINER_NAME)" = "podman" ]; then \
		podman machine init --cpus 2 --memory 2048 --disk-size 20 2>/dev/null || echo "Machine already exists"; \
	else \
		echo "Podman not detected, skipping..."; \
	fi

# Podman-specific: Start machine
podman-start:
	@if [ "$(CONTAINER_NAME)" = "podman" ]; then \
		podman machine start 2>/dev/null || echo "Machine already running or not initialized"; \
	else \
		echo "Podman not detected, skipping..."; \
	fi

# Podman-specific: Check status
podman-status:
	@if [ "$(CONTAINER_NAME)" = "podman" ]; then \
		echo "=== Podman Info ==="; \
		podman version; \
		echo ""; \
		echo "=== Machine Status ==="; \
		podman machine list 2>/dev/null || echo "No machine (Linux native)"; \
		echo ""; \
		echo "=== Running Containers ==="; \
		podman ps; \
	else \
		echo "Podman not detected"; \
		echo "Using: $(CONTAINER_ENGINE)"; \
	fi

# Legacy docker aliases (for backwards compatibility)
docker: container
docker-build: container-build
docker-dev: container-dev
docker-stop: container-stop

# Clean up Python cache files
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
	@echo "For containerized deployment:"
	@if [ "$(CONTAINER_NAME)" = "podman" ]; then \
		echo "  - Podman detected! Run 'make podman-start' first (macOS)"; \
		echo "  - Then 'make container' to build and run"; \
	else \
		echo "  - Run 'make container' to build and run with Docker"; \
	fi
	@echo ""
