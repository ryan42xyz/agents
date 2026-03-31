# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Directory Is

Oncall knowledge base for SRE incident response. Contains structured reference material — not runnable code.

## Navigation

**Start with `README.md`** — it is the full index of every file by kind, tags, first action, and summary. Use it as the primary lookup table before searching.

**`agent-routing-table.md`** — first-decision layer for incoming alert signals. Routes by symptom (refused/timeout/lag/P99/pending/evicted/AccessDenied) to the appropriate triage cluster and policy.

## Directory Structure

| Directory | Content |
|-----------|---------|
| `cards/` | Fast-triage reference cards — minimal commands for the first 2 minutes |
| `runbooks/` | Step-by-step execution procedures with `#MANUAL` markers for human gates |
| `checklists/` | Layered troubleshooting sequences |
| `patterns/` | Root cause models and recurring failure patterns |
| `debug-trees/` | Structured decision trees with MCP tool calls + branching logic for autonomous investigation |
| `references/` | Command references, architecture overviews, monitoring links, operational lookups |
| `cases/` | Incident postmortems; `.incident.md` = structured record, `.trace.md` = agent decision trace |
| `pic/` | Screenshots referenced by cases and runbooks |

## File Naming Convention

`{kind}-{description}.md` — kind is one of: `card`, `runbook`, `checklist`, `pattern`, `reference`, `case`, `debug-tree`

## Frontmatter Schema

Every file carries:
```yaml
metadata:
  kind: <kind>
  status: draft | stable
  summary: "<one-line description>"
  tags: ["tag1", "tag2"]
  first_action: "<first diagnostic step>"
```

Use `first_action` to jump directly to the first command when responding to a live incident.

## Oncall Invariants

These apply to every incident regardless of type:

1. **Read-only first** — all diagnostic steps are read-only until root cause is confirmed
2. **Human gate before action** — any state-changing command needs explicit approval; look for `#MANUAL` markers in runbooks
3. **Blast radius before fix** — assess scope before applying any mitigation
4. **Evidence chain required** — causal claims must be supported by time-aligned evidence
5. **Mitigation ≠ fix** — short-term restart/workaround is not a structural fix; always note follow-ups

## Adding New Content

- Match the existing frontmatter schema
- Use `first_action` to capture the first diagnostic step
- Update `README.md` index table when adding new files
- `.trace.md` files capture agent decision traces for learning; `.incident.md` files are the structured incident record
