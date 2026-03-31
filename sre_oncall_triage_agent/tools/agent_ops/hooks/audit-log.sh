#!/bin/bash
# audit-log.sh — PostToolUse hook for K8s/AWS audit trail
# Appends structured JSONL to ~/.agent-audit/YYYY-MM-DD.jsonl
# Only logs commands that touch K8s/AWS/infra tooling

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only log infra-related commands
if ! echo "$CMD" | grep -qE '^(kubectl|helm|aws|eksctl|k9s|kubectx|kubens|terraform|terragrunt|kafsouth|kwest|keast|keu|ksg[ab]|kasiasedcube|kgcpwest|kca)'; then
  exit 0
fi

# Resolve symlinks to find the real script location, so logs always go to repo/logs/
_REAL=$(python3 -c "import os,sys; print(os.path.realpath('${BASH_SOURCE[0]}'))")
AUDIT_DIR="$(dirname "$_REAL")/../logs"
mkdir -p "$AUDIT_DIR"

DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG_FILE="$AUDIT_DIR/${DATE}.jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // "unknown"' 2>/dev/null)

# Extract stdout/stderr separately so truncation never breaks the JSON envelope
RAW_STDOUT=$(echo "$INPUT" | jq -r '.tool_response.stdout // ""' 2>/dev/null | head -c 500)
RAW_STDERR=$(echo "$INPUT" | jq -r '.tool_response.stderr // ""' 2>/dev/null | head -c 200)

# Build JSONL entry
ENTRY=$(jq -cn \
  --arg ts "$TIMESTAMP" \
  --arg sid "$SESSION_ID" \
  --arg cwd "$CWD" \
  --arg cmd "$CMD" \
  --arg stdout "$RAW_STDOUT" \
  --arg stderr "$RAW_STDERR" \
  '{phase: "post", timestamp: $ts, session_id: $sid, cwd: $cwd, command: $cmd, stdout: $stdout, stderr: $stderr}')

echo "$ENTRY" >> "$LOG_FILE"
exit 0
