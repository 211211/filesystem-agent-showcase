"""Demo of the unified dependency injection system.

This example shows how to use the new dependency injection patterns
in app/dependencies.py for creating agents with proper factory-based
dependency injection.
"""

import asyncio
from pathlib import Path

from app.dependencies import (
    get_settings,
    get_session_repository,
    get_tool_registry,
    get_agent_factory_dependency,
    get_agent,
    reset_dependencies,
)


async def demo_basic_dependencies():
    """Demo 1: Basic dependency access."""
    print("\n=== Demo 1: Basic Dependencies ===")

    # Get settings singleton
    settings = get_settings()
    print(f"Settings: {settings.azure_openai_deployment_name}")

    # Get session repository singleton
    repo = get_session_repository()
    print(f"Session Repository: {type(repo).__name__}")

    # Get tool registry singleton
    registry = get_tool_registry()
    print(f"Tool Registry: {len(registry)} tools registered")
    print(f"Available tools: {', '.join(registry.list_names())}")

    # Get agent factory singleton
    factory = get_agent_factory_dependency()
    print(f"Agent Factory: {type(factory).__name__}")


async def demo_agent_creation():
    """Demo 2: Creating agents via factory."""
    print("\n=== Demo 2: Agent Creation ===")

    # Create agent using default settings
    agent = get_agent()
    print(f"Agent created: {type(agent).__name__}")
    print(f"Data root: {agent.data_root}")
    print(f"Parallel execution: {agent.parallel_execution}")

    # Create a test session
    repo = get_session_repository()
    session = await repo.get_or_create("demo-session")
    print(f"Session created: {session.session_id}")

    # Example query
    response = await agent.chat("List files in the data directory", history=[])
    print(f"Agent response: {response.message[:100]}...")


async def demo_custom_settings():
    """Demo 3: Agent with custom settings."""
    print("\n=== Demo 3: Custom Settings ===")

    # Get settings and modify (in production, use environment variables)
    settings = get_settings()

    # Create agent with specific settings
    agent = get_agent(settings=settings)
    print(f"Agent with custom settings: {type(agent).__name__}")


async def demo_tool_registry():
    """Demo 4: Working with tool registry."""
    print("\n=== Demo 4: Tool Registry ===")

    registry = get_tool_registry()

    # List all tools
    print("Registered tools:")
    for tool_name in registry.list_names():
        tool = registry.get(tool_name)
        print(f"  - {tool_name}: {tool.description}")
        print(f"    Cacheable: {tool.cacheable}, TTL: {tool.cache_ttl}")

    # Build a command
    grep_cmd = registry.build_command("grep", {
        "pattern": "TODO",
        "path": ".",
        "recursive": True,
        "ignore_case": True
    })
    print(f"\nGrep command: {' '.join(grep_cmd)}")


async def demo_singleton_behavior():
    """Demo 5: Singleton behavior."""
    print("\n=== Demo 5: Singleton Behavior ===")

    # All dependencies are singletons
    settings1 = get_settings()
    settings2 = get_settings()
    print(f"Settings singleton: {settings1 is settings2}")

    repo1 = get_session_repository()
    repo2 = get_session_repository()
    print(f"Repository singleton: {repo1 is repo2}")

    registry1 = get_tool_registry()
    registry2 = get_tool_registry()
    print(f"Registry singleton: {registry1 is registry2}")

    factory1 = get_agent_factory_dependency()
    factory2 = get_agent_factory_dependency()
    print(f"Factory singleton: {factory1 is factory2}")

    # But agents are created fresh each time
    agent1 = get_agent()
    agent2 = get_agent()
    print(f"Agents are unique: {agent1 is not agent2}")


async def demo_reset():
    """Demo 6: Resetting dependencies (for testing)."""
    print("\n=== Demo 6: Reset Dependencies ===")

    # Get initial instances
    settings1 = get_settings()
    repo1 = get_session_repository()

    print(f"Initial settings: {id(settings1)}")
    print(f"Initial repository: {id(repo1)}")

    # Reset all dependencies
    reset_dependencies()
    print("Dependencies reset!")

    # Get new instances
    settings2 = get_settings()
    repo2 = get_session_repository()

    print(f"New settings: {id(settings2)}")
    print(f"New repository: {id(repo2)}")
    print(f"Settings changed: {settings1 is not settings2}")
    print(f"Repository changed: {repo1 is not repo2}")


async def demo_fastapi_integration():
    """Demo 7: FastAPI integration pattern."""
    print("\n=== Demo 7: FastAPI Integration ===")

    # Example of how to use in FastAPI routes
    example_code = """
    from fastapi import APIRouter, Depends
    from app.dependencies import get_agent, get_session_repository
    from app.agent.filesystem_agent import FilesystemAgent
    from app.repositories.session_repository import SessionRepository

    router = APIRouter()

    @router.post("/chat")
    async def chat(
        message: str,
        agent: FilesystemAgent = Depends(get_agent),
        repo: SessionRepository = Depends(get_session_repository),
    ):
        # Agent and repository are automatically injected
        session = await repo.get_or_create("session-id")
        response = await agent.chat(message, history=session.get_history())
        return {"response": response.message}
    """
    print(example_code)


async def main():
    """Run all demos."""
    print("=" * 60)
    print("Dependency Injection System Demo")
    print("=" * 60)

    await demo_basic_dependencies()
    await demo_agent_creation()
    await demo_custom_settings()
    await demo_tool_registry()
    await demo_singleton_behavior()
    await demo_reset()
    await demo_fastapi_integration()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
