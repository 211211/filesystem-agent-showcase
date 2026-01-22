#!/bin/bash
# Test API endpoints for filesystem-agent-showcase

set -e

BASE_URL="http://localhost:8000"

echo "=== Testing Filesystem Agent API ==="
echo ""

# 1. Health check
echo "1. Health Check"
echo "   GET ${BASE_URL}/health"
curl -s "${BASE_URL}/health" | jq .
echo ""

# 2. List markdown files
echo "2. List Markdown Files"
echo "   POST ${BASE_URL}/api/chat"
curl -s -X POST "${BASE_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "List all markdown files in the data directory"}' | jq .
echo ""

# 3. Find Python files
echo "3. Find Python Files"
curl -s -X POST "${BASE_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find all Python files"}' | jq .
echo ""

# 4. Read a file
echo "4. Read README.md"
curl -s -X POST "${BASE_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the contents of data/README.md"}' | jq .
echo ""

# 5. Search in files
echo "5. Search for 'cache' in markdown files"
curl -s -X POST "${BASE_URL}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Search for the word cache in all markdown files"}' | jq .
echo ""

echo "=== Tests Complete ==="
