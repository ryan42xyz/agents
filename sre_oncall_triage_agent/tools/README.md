# Infra Tools

Small, read-only helpers for oncall workflows. These tools may query monitoring endpoints but never mutate production systems.

## Tool Overview

| Tool | Purpose | When to use |
|---|---|---|
| `vm_lookup.py` | Discover pods/namespaces from VictoriaMetrics | Missing `namespace`/`pod` in checklist |
| `loki_fetch/` | Parse a Grafana Explore URL → LogQL + timestamps (JSON) | Extract LogQL from a Grafana URL before calling `mcp__grafana__query_loki_logs` |
| `agent_ops/` | K8s/AWS safety gate + audit trail | Always active via Claude Code hooks (`~/.claude/hooks/`) |
| `agent_ops/verify.py` | Verify investigation output completeness and quality | Run after writing output file (mandatory) |
| `agent_ops/slo.py` | Aggregate investigation quality metrics | Periodic review of agent effectiveness |

> **Metrics queries** (PromQL/MetricsQL) → use the **`mcp__victoriametrics__*` MCP tools** directly (not vm_lookup.py). vm_lookup.py is only for pod/namespace discovery.

---

## `vm_lookup.py`

Queries VictoriaMetrics via the Prometheus-compatible API:

- Base: `$VM_BASE_URL` (set in `.env` or environment)
- Endpoint: `/prometheus/api/v1/query`

Examples:

```bash
# List candidate FP pods in a cluster (returns JSON)
python3 skills/.infra/tools/vm_lookup.py pods --cluster aws-useast1-prod-b --service fp

# Same, but prefer prod namespace in ranking (does not hide other namespaces)
python3 skills/.infra/tools/vm_lookup.py pods --cluster aws-useast1-prod-b --service fp --prefer-namespace prod

# Get namespace for a known pod
python3 skills/.infra/tools/vm_lookup.py namespace-from-pod --pod fp-deployment-957745bf6-wdrqx
```

---

## `agent_ops/verify.py`

Deterministic verifier for investigation output files. Checks schema completeness, debug tree step completion, conclusion-evidence consistency, Slack language conservatism, and link validity.

```bash
# Verify an output file (mandatory after every investigation)
python3 tools/agent_ops/verify.py tmp/sre-triage-2026-03-31_14-23-45.md

# JSON output for programmatic use
python3 tools/agent_ops/verify.py tmp/sre-triage-2026-03-31_14-23-45.md --json
```

Exit codes: 0=PASS, 1=WARN, 2=FAIL.

---

## `agent_ops/slo.py`

Aggregates quality metrics from investigation output files. Tracks debug tree usage rate, verdict distribution, steps to conclusion, verification pass rate, and more.

```bash
# All investigations
python3 tools/agent_ops/slo.py

# Since a specific date
python3 tools/agent_ops/slo.py --since 2026-03-01

# JSON output
python3 tools/agent_ops/slo.py --json
```
