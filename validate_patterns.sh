#!/bin/bash

# Design Pattern Implementation Validation
# Tests all implemented patterns: Repository, Factory, Handler Chain

set -e

echo "🧪 Design Pattern Implementation Validation"
echo "==========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PASS=0
FAIL=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -n "Testing: $test_name... "
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAIL++))
    fi
}

echo "1️⃣  Foundation Patterns"
run_test "Exception Hierarchy" "poetry run python -c 'from app.exceptions import FilesystemAgentException'"
run_test "Configuration Objects" "poetry run python -c 'from app.config.agent_config import AgentConfig'"
run_test "Repository Base" "poetry run python -c 'from app.repositories.base import Repository'"
run_test "Session Repository" "poetry run python -c 'from app.repositories import SessionRepository'"

echo ""
echo "2️⃣  Factory & Registry"
run_test "Tool Registry (7 tools)" "poetry run python -c 'from app.repositories.tool_registry import create_default_registry; assert len(create_default_registry()) == 7'"
run_test "Component Factory" "poetry run python -c 'from app.factories import ComponentFactory'"
run_test "Agent Factory" "poetry run python -c 'from app.factories import get_agent_factory'"
run_test "Dependencies System" "poetry run python -c 'from app.dependencies import get_agent'"

echo ""
echo "3️⃣  Handler Chain"
run_test "Tool Handlers" "poetry run python -c 'from app.agent.handlers import ToolHandler, create_handler_chain'"

echo ""
echo "4️⃣  Integration"
run_test "Factory creates agent" "poetry run python -c 'from app.dependencies import get_agent; agent = get_agent()'"
run_test "Agent has registry" "poetry run python -c 'from app.dependencies import get_agent; assert get_agent().tool_registry is not None'"

echo ""
echo "5️⃣  Test Suite"
run_test "All tests pass" "poetry run pytest tests/ -q --tb=no"

echo ""
echo "════════════════════════════════════════"
echo "Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "════════════════════════════════════════"
[ $FAIL -eq 0 ] && echo -e "${GREEN}✅ ALL VALIDATED${NC}" || echo -e "${RED}❌ FAILED${NC}"
exit $FAIL
