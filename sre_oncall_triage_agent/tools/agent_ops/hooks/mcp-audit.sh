#!/bin/bash
# mcp-audit.sh — PostToolUse hook: audit MCP tool calls
# Captures victoriametrics, grafana, loki MCP tool usage to JSONL audit log.
# These calls are invisible to k8s-gate.sh and audit-log.sh (which only see Bash commands).

INPUT=$(cat)

# Extract tool name from the hook input
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# Only audit MCP tool calls
case "$TOOL_NAME" in
  mcp__victoriametrics__*|mcp__grafana__*|mcp__slack__*)
    ;;
  *)
    exit 0
    ;;
esac

# Resolve symlinks to find logs directory
_REAL=$(python3 -c "import os,sys; print(os.path.realpath('${BASH_SOURCE[0]}'))")
AUDIT_DIR="$(dirname "$_REAL")/../logs"
mkdir -p "$AUDIT_DIR"

DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG_FILE="$AUDIT_DIR/mcp-${DATE}.jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)

# Extract tool input parameters (first 1000 chars to prevent log bloat)
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' 2>/dev/null | head -c 1000)

# Extract response summary (first 500 chars)
RESPONSE_SUMMARY=$(echo "$INPUT" | jq -r '.tool_response.content // .tool_response // "no response"' 2>/dev/null | head -c 500)

# Build JSONL entry
ENTRY=$(jq -cn \
  --arg ts "$TIMESTAMP" \
  --arg sid "$SESSION_ID" \
  --arg tool "$TOOL_NAME" \
  --arg input "$TOOL_INPUT" \
  --arg response "$RESPONSE_SUMMARY" \
  '{timestamp: $ts, session_id: $sid, tool: $tool, input: $input, response_preview: $response}')

echo "$ENTRY" >> "$LOG_FILE"
exit 0
