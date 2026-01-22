#!/bin/bash
# Test script for filesystem agent

BASE_URL="http://localhost:8000/api/chat"

questions=(
  "What projects exist in the data folder?"
  "What are the password requirements in the security policy?"
  "Find all files mentioning authentication"
  "Compare the evaluation results between FS-Explorer and RAG"
  "How does parallel processing affect side-channel power analysis attacks?"
)

for q in "${questions[@]}"; do
  echo "===== Question: $q ====="
  response=$(curl -s -X POST "$BASE_URL" -H "Content-Type: application/json" -d "{\"message\": \"$q\"}")
  echo "$response" | jq -r '.response' 2>/dev/null || echo "$response"
  echo ""
  echo "---"
  echo ""
done
