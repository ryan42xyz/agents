#!/bin/bash
# audit-pre.sh — PreToolUse hook: log mutating infra ops BEFORE execution
# Creates a "pre" entry that pairs with audit-log.sh's "post" entry.
# Readable post-mortem pattern: grep phase=pre shows intent, phase=post shows outcome.

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only care about infra commands
if ! echo "$CMD" | grep -qE '^(kubectl|helm|aws|eksctl|kafsouth|kwest|keast|keu|ksg[ab]|kasiasedcube|kgcpwest|kca)'; then
  exit 0
fi

# Only log mutating operations — skip reads
MUTATING_PAT=" (apply|create|scale|patch|delete|drain|cordon|taint|rollout restart|exec|cp|run )"
HELM_MUTATING_PAT="^helm (upgrade|install|uninstall|rollback)"

if ! echo "$CMD" | grep -qE "$MUTATING_PAT" && ! echo "$CMD" | grep -qE "$HELM_MUTATING_PAT"; then
  exit 0
fi

_REAL=$(python3 -c "import os,sys; print(os.path.realpath('${BASH_SOURCE[0]}'))")
AUDIT_DIR="$(dirname "$_REAL")/../logs"
mkdir -p "$AUDIT_DIR"

DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG_FILE="$AUDIT_DIR/${DATE}.jsonl"

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // "unknown"' 2>/dev/null)

# Extract # INTENT: comment from the command (first matching line)
REASONING=$(echo "$CMD" | sed -n 's/^# INTENT: //p' | head -1)

ENTRY=$(jq -cn \
  --arg phase "pre" \
  --arg ts "$TIMESTAMP" \
  --arg sid "$SESSION_ID" \
  --arg cwd "$CWD" \
  --arg cmd "$CMD" \
  --arg reasoning "$REASONING" \
  '{phase: $phase, timestamp: $ts, session_id: $sid, cwd: $cwd, command: $cmd, reasoning: (if $reasoning == "" then null else $reasoning end)}')

echo "$ENTRY" >> "$LOG_FILE"
exit 0
