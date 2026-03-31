---
metadata:
  kind: reference
  status: draft
  summary: "Knowledge base index — template for creating your own README.md"
  tags: ["index", "oncall", "case-library"]
  first_action: "Copy this to README.md and populate with your own cases"
---

# Knowledge Base Index (Template)

This is a template. Copy to `README.md` and populate with your own operational knowledge.

The actual `README.md` is gitignored because it contains client-specific file references.

## Structure

Organize files by kind using the table format below:

### Fast Reference Cards

| File | Tags | Purpose |
|------|------|---------|
| `cards/card-<topic>.md` | `tag1, tag2` | What this card helps triage |

### Cases

| File | Tags | First Action | Summary |
|------|------|-------------|---------|
| `cases/case-<description>.md` | `tag1, tag2` | First diagnostic step | One-line summary |
| `cases/case-<description>.incident.md` | — | — | Structured incident record |
| `cases/case-<description>.trace.md` | — | — | Decision trace for agent learning |

### Runbooks

| File | Tags | First Action | Summary |
|------|------|-------------|---------|
| `runbooks/runbook-<topic>.md` | `tag1, tag2` | First step | Step-by-step procedure with `#MANUAL` gates |

### Debug Trees

| File | Tags | Routing Cluster | Summary |
|------|------|----------------|---------|
| `debug-trees/debug-tree-<pattern>.md` | `tag1, tag2` | Cluster N | Executable decision tree with MCP tool calls |

### Patterns

| File | Tags | Summary |
|------|------|---------|
| `patterns/pattern-<name>.md` | `tag1, tag2` | Recurring failure model |

### Checklists

| File | Tags | Summary |
|------|------|---------|
| `checklists/checklist-<topic>.md` | `tag1, tag2` | Layered troubleshooting sequence |

### References

| File | Tags | Summary |
|------|------|---------|
| `references/reference-<topic>.md` | `tag1, tag2` | Operational lookup (gitignored — see `references/README.md`) |
