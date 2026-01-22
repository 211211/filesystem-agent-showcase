"""
Filesystem Agent Showcase - Main FastAPI Application

A demonstration of building AI agents using filesystem and bash tools,
inspired by Vercel's approach to agentic AI.

Learn more: https://vercel.com/blog/how-to-build-agents-with-filesystems-and-bash
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.routes import chat_router, documents_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("Starting Filesystem Agent Showcase")
    logger.info(f"Data root: {settings.data_root}")
    logger.info(f"Sandbox enabled: {settings.sandbox_enabled}")

    # Ensure data directory exists
    settings.data_root.mkdir(parents=True, exist_ok=True)

    yield

    logger.info("Shutting down Filesystem Agent Showcase")


# Create FastAPI application
app = FastAPI(
    title="Filesystem Agent Showcase",
    description="""
## Overview

This API demonstrates how to build AI agents that leverage filesystem and bash tools
for document exploration and analysis. Inspired by Vercel's approach to agentic AI.

## Key Features

- **Intelligent Document Q&A**: Ask questions about your documents and get AI-powered answers
- **Filesystem Exploration**: The agent can search, read, and analyze files using bash tools
- **Secure Sandbox**: All file operations are confined to a designated data directory
- **Transparent Tool Calls**: See exactly which commands the agent executes

## Getting Started

1. Upload documents to the `/api/documents` endpoint or place them in the `data/` directory
2. Use the `/api/chat` endpoint to ask questions about your documents
3. The agent will use tools like `grep`, `find`, `cat`, and `ls` to find answers

## Example Queries

- "What files are in the projects folder?"
- "Find all markdown files that mention authentication"
- "Summarize the README in project-alpha"
- "Search for TODO comments in the codebase"
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat_router, prefix="/api")
app.include_router(documents_router, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Filesystem Agent Showcase",
        "version": "0.1.0",
        "description": "AI Agent using filesystem and bash tools for document Q&A",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "data_root_exists": settings.data_root.exists(),
        "sandbox_enabled": settings.sandbox_enabled,
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
