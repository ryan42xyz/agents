# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

This repo contains the **SRE Oncall Triage Agent** — an autonomous investigation agent for production alerts. It triages Slack/alert input, executes read-only investigation via MCP tool calls (VictoriaMetrics, Grafana, Loki), and produces Slack-ready findings with a complete evidence chain. It never mutates production systems.

The agent is delivered as a **Claude Code skill + hook chain**, not a standalone binary. There is no build step.

## Setup

```bash
cd sre_oncall_triage_agent
cp .env.example .env          # fill in VM_BASE_URL, GRAFANA_URL, LOKI_URL, etc.
bash tools/agent_ops/setup.sh # installs hooks → ~/.claude/hooks/ and updates settings.json
```

`setup.sh` symlinks hook scripts and merges `hooks-manifest.json` into `~/.claude/settings.json`. Re-run whenever hooks change.

## Key Operational Commands

```bash
# Verify a triage output file
python tools/agent_ops/verify.py tmp/sre-triage-YYYY-MM-DD_HH-MM-SS.md

# Aggregate quality metrics across all investigations
python tools/agent_ops/slo.py
python tools/agent_ops/slo.py --since 2025-01-01

# View K8s/MCP audit logs in readable form
python tools/agent_ops/audit-view.py tools/agent_ops/logs/YYYY-MM-DD.jsonl
python tools/agent_ops/audit-view.py tools/agent_ops/logs/mcp-YYYY-MM-DD.jsonl

# Parse a Grafana Explore URL into LogQL + timestamps
python tools/loki_fetch/parse_grafana_url.py "<url>"

# Look up candidate pods/namespaces in VictoriaMetrics
python tools/vm_lookup.py --service <name> --cluster <cluster>
```

`verify.py` exit codes: `0`=PASS, `1`=WARN (review before sending), `2`=FAIL (fix required).

## Architecture

### Investigation Pipeline

```
Alert input
  → Signal extraction (FACETS/signal_extraction.md)
  → Routing (knowledge/agent-routing-table.md → one of 6 clusters)
  → Debug tree match? YES → execute MCP steps → conclude
                     NO  → FACETS-based checklist → manual inspection
  → Write output file (tmp/sre-triage-YYYY-MM-DD_HH-MM-SS.md)
  → verify.py → PASS/WARN/FAIL
  → Slack response
```

### Three Safety Layers

1. **Claude Code permissions** (`settings.json`) — whitelist `kubectl get/describe/logs`; deny delete/drain/IAM mutations.
2. **Hook chain** (`tools/agent_ops/hooks/`) — four hooks:
   - `k8s-gate.sh` — tier enforcement (PROD/PCI=read-only, PREPROD=dry-run, DEV=permissive)
   - `audit-pre.sh` — captures `# INTENT:` comment before any mutation
   - `audit-log.sh` — JSONL audit trail for K8s commands
   - `mcp-audit.sh` — JSONL audit trail for MCP calls
3. **Agent spec** (`SKILL.md`) — hard constraint: read-only investigation only; query safety rules enforced.

### Query Safety Rules (all MCP queries)

| Rule | Constraint |
|------|-----------|
| Label filter required | Every PromQL query must include ≥1 label filter (namespace/job/service) |
| Step floor | `query_range` step ≥ 30s |
| Time window ceiling | `query_range` ≤ 24h; Loki ≤ 6h |
| Loki stream selector | Every LogQL must include ≥1 stream selector |
| No regex wildcard on high-cardinality labels | Avoid `=~".*"` on pod/instance/container |
| Retry budget | Max 2 retries per query |

### Knowledge Base Layout

```
knowledge/
  agent-routing-table.md    # signal → one of 6 triage clusters (read first)
  README.md                 # master index of all 130+ files by kind/tag/summary
  CLAUDE.md                 # oncall invariants: read-only, evidence chain, human gate
  debug-trees/              # 7 executable decision trees (primary investigation path)
  cases/                    # ~34 incident postmortems
  runbooks/                 # ~21 procedures with #MANUAL gates
  cards/                    # ~15 fast-triage reference cards
  patterns/                 # 4 root cause models
  checklists/               # 3 layered troubleshooting sequences
  references/               # command refs, architecture diagrams, links
FACETS/                     # 10 structured knowledge facets (signal extraction, etc.)
```

**When adding knowledge files**, use the frontmatter schema:
```yaml
metadata:
  kind: case | runbook | card | pattern | reference | checklist | debug-tree
  status: draft | stable | final
  summary: "<one-line description>"
  tags: ["tag1", "tag2"]
  first_action: "<first diagnostic step>"
```

### 6 Triage Clusters

| # | Cluster | Key Signals |
|---|---------|------------|
| 1 | Routing/Ingress/DNS | connection refused, timeout, DNS failure |
| 2 | Scheduling/Node Pressure | pod Pending, Evicted, DiskPressure |
| 3 | Stateful Write Pressure | Kafka lag, DB backlog |
| 4 | Observability/False Signals | P99 high but error rate normal |
| 5 | Identity/Access | AccessDenied, 403, UnauthorizedOperation |
| 6 | Change Management | regression post-upgrade/deploy |

### Mandatory Output Format

Every investigation writes `tmp/sre-triage-YYYY-MM-DD_HH-MM-SS.md` with sections (in order):
1. Investigation Scope (YAML: cluster, services, namespaces, tools, time_window, out_of_scope)
2. Slack Response (Impact, Status, Immediate Action, Next Steps, Escalation criteria)
3. Internal Notes (triage result, conclusion, event type, hypothesis tree, evidence checklist, uncertainty note)
4. Extracted Signals (alertname, severity, cluster, namespace, pod, service, time_window, missing_fields)
5. Links (ready URLs / templates / lookups)
6. Investigation Log (debug tree table: Step|Tool|Query|Result|Interpretation|Branch) or FACETS checklist
7. Historical Pattern Matches (optional)
8. Verification (appended by verify.py)

### Verdict vocabulary

`IGNORE_DEV` | `KNOWN_ISSUE` | `NON_ACTIONABLE_NOISE` | `NEEDS_ATTENTION` | `ESCALATE` | `MANUAL`

Conclusion sentences must use hedged language: "likely", "possibly", "unclear" — never "root cause is" or "definitely".

## Files to Read Before Modifying the Agent

- `SKILL.md` — full agent specification (goals, hard constraints, output format, on-error handling)
- `ARCHITECTURE.md` — GCORF framework, safety layer details, audit observability design
- `knowledge/agent-routing-table.md` — routing logic (changing this changes investigation paths)
- `hooks-manifest.json` — source of truth for hook registration (re-run `setup.sh` after edits)
