# SRE Oncall Triage Agent

An AI agent for evidence-backed oncall investigation. Takes a raw alert or Slack message, autonomously queries metrics/logs via MCP tools, and produces a structured output with a ready-to-send Slack response.

**Safety boundary**: read-only investigation only. Never mutates production systems.

---

## How it works

1. **Triage** — extracts signals from the alert, routes to one of 6 triage clusters via `knowledge/agent-routing-table.md`
2. **Investigate** — executes a matching debug tree (or falls back to a FACETS-based checklist), calling VictoriaMetrics and Grafana MCP tools for each step
3. **Report** — writes `tmp/sre-triage-<timestamp>.md` with a Slack response, internal notes, evidence log, and links; runs `verify.py` before sending

## Usage

Invoke via the `sre_oncall_triage_agent` skill in Claude Code:

```
/sre_oncall_triage_agent
```

Then paste the alert or Slack message. The agent reads the knowledge base, executes the debug tree, and writes the output file.

## Directory layout

```
sre_oncall_triage_agent/
├── SKILL.md              # Agent spec: goal, output format, hard constraints
├── ARCHITECTURE.md       # GCORF design framework + Mermaid diagrams
├── FACETS/               # Structured knowledge facets (signal extraction, logs, pods, traffic, …)
├── knowledge/            # All oncall knowledge (cases, runbooks, cards, debug trees, patterns, refs)
│   ├── README.md         # Master index — start here when searching knowledge
│   ├── agent-routing-table.md  # Signal → triage cluster routing (read first during triage)
│   └── CLAUDE.md         # Oncall invariants (read-only, human gate, blast radius, evidence chain)
└── tools/
    ├── vm_lookup.py      # Pod/namespace discovery from VictoriaMetrics
    ├── loki_fetch/       # Parse Grafana Explore URLs → LogQL + timestamps
    └── agent_ops/        # Safety gate + audit trail (always active via hooks)
        ├── hooks/        # k8s-gate.sh, audit-pre.sh, audit-log.sh, mcp-audit.sh
        ├── verify.py     # Output verifier (mandatory after every investigation)
        └── slo.py        # Aggregate investigation quality metrics
```

## Knowledge base

| Directory | Kind | Contents |
|-----------|------|----------|
| `cases/` | case | Incident records with evidence, timeline, decision trace |
| `runbooks/` | runbook | Step-by-step procedures with `#MANUAL` gates |
| `cards/` | card | Fast-triage reference cards (first 2 minutes) |
| `debug-trees/` | debug-tree | Structured decision trees with MCP tool calls |
| `patterns/` | pattern | Root cause models (FP latency, ingress 429, ClickHouse merge, networking) |
| `checklists/` | checklist | Layered troubleshooting sequences |
| `references/` | reference | Command refs, architecture docs, dashboards, cluster/client lookups |

## Data sources

| Source | MCP tools | Use for |
|--------|-----------|---------|
| VictoriaMetrics | `mcp__victoriametrics__query_range`, `query`, `series`, `rules`, `metrics` | PromQL/MetricsQL queries |
| Grafana / Loki | `mcp__grafana__query_loki_logs`, `query_prometheus`, `search_dashboards` | LogQL, dashboard inspection |

**Query safety rules** (enforced by agent spec):
- Every PromQL query must include a label filter (`namespace`, `job`, or `service`)
- `query_range` step ≥ 30s; time window ≤ 24h
- Every LogQL query must include a stream selector label
- Max 2 retries per query; on failure, `MARK_UNKNOWN` and continue

## Safety layers

Three layers of defense, outer to inner:

1. **Claude Code permissions** (`settings.json`) — allowlist of read-only kubectl ops; explicit deny for destructive commands
2. **Hook chain** (`tools/agent_ops/hooks/`) — environment tier enforcement (PROD mutations blocked), INTENT logging, K8s and MCP audit JSONL
3. **Agent spec** — hard read-only constraint, scope declaration, query safety rules, deterministic debug tree branching

## Output

The agent writes `tmp/sre-triage-<timestamp>.md` containing:

- **Slack Response** — conservative, ready-to-send oncall reply
- **Internal Notes** — triage verdict, conclusion, hypothesis tree, evidence checklist
- **Extracted Signals** — signals from the alert (no inference)
- **Links** — ready/template URLs for Grafana, VMUI, VMAlert
- **Investigation Log** — step-by-step table: Tool / Query / Result / Branch

After writing, `verify.py` checks schema completeness, evidence-conclusion consistency, and Slack language conservatism. Exit 0=PASS, 1=WARN, 2=FAIL.

## Post-investigation

After verification, the agent offers to save the case to `knowledge/cases/` and propose new debug trees for paths not yet covered.

Quality trends: `python3 tools/agent_ops/slo.py [--since YYYY-MM-DD] [--json]`
