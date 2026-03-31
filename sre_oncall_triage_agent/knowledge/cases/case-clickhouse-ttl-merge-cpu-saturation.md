---
metadata:
  kind: case
  status: draft
  summary: "ClickHouse CPU saturated at 92% (27.6/30 cores) due to query + merge superposition: 3 concurrent SELECT * full-table scans on tenant_a.event_result (~700M rows each) are the primary consumer (~20+ cores), TTL/rewrite merges are secondary (~3 cores)."
  tags: ["clickhouse", "cpu", "merge", "ttl", "query", "full-table-scan", "event_result"]
  first_action: "system.processes + top -H: determine whether CPU is from queries or merges before concluding"
  related:
    - "patterns/pattern-clickhouse-merge-cpu-root-cause.md"
    - "cards/card-clickhouse-merge-pressure-fast-signals.md"
    - "cases/case-clickhouse-copydata-recovery-failure.md"
---

# ClickHouse CPU Saturation: Query + Merge Superposition

## TL;DR (Do This First)

1. Confirm CPU is near limit: `rate(container_cpu_usage_seconds_total{pod=..., container="clickhouse"}[5m])` vs resource limits
2. **Exec into pod → run both diagnostic commands (see below) — do NOT skip either one**
3. Check pod restarts (should be 0 if this is sustained load, not OOM)
4. Compare CPU across clusters — if isolated, it's workload-specific, not fleet-wide

## Critical Lesson Learned

> **`system.merges` alone is insufficient to determine CPU root cause.**
>
> In this incident, initial investigation found 3 active merges and concluded "merge debt." Follow-up with `system.processes` and `top -H` revealed that **queries were the dominant consumer (~67%+ CPU)**, while merges only contributed ~10%.
>
> Always run **both** commands before concluding.

## The Two Diagnostic Commands

### Command 1: system.processes (what queries are running)

```sql
SELECT query_id, elapsed, read_rows, memory_usage, query
FROM system.processes
ORDER BY elapsed DESC LIMIT 10;
```

**What to look for**:
- Long-running SELECTs with high `read_rows` → full-table scans
- `SELECT *` patterns → reading unnecessary columns
- Multiple concurrent expensive queries → superposition effect
- INSERTs with very high `memory_usage` → wide-table write pressure

### Command 2: top -H (which threads consume CPU)

```bash
top -H -b -n 1 | head -30
```

**What to look for**:
- **MergeMutate** threads high → merge/TTL is the CPU driver
- **QueryPipelineEx** threads high → queries are the CPU driver
- **Both high** → superposition (this case)
- **AsyncMetrics** high → monitoring overhead
- Load average vs core count → overload indicator

### Decision Matrix

| system.processes | top -H dominant | Conclusion |
|------------------|----------------|------------|
| No expensive queries | MergeMutate | Merge debt (pattern doc applies) |
| Expensive queries | QueryPipelineEx | **Query is root cause** |
| Expensive queries | Both MergeMutate + QueryPipelineEx | **Superposition** (this case) |
| No expensive queries | QueryPipelineEx | Short-lived query burst; check query_log |

## Safety Boundaries

- **Read-only**: all diagnostic steps are read-only
- `#MANUAL` gate: any merge kill, query kill, or config change requires human approval

## Signals

- **Alert**: ClickHouse container high CPU usage (90-95%)
- **Cluster**: &lt;cluster-name&gt;
- **Pod**: &lt;pod-name&gt; (ClickHouse Operator StatefulSet)
- **Namespace**: &lt;namespace&gt;
- **Container**: clickhouse

## Evidence Chain

| Step | Finding |
|------|---------|
| Container CPU | 27.6 / 30 cores (92%) — confirmed via VictoriaMetrics |
| CPU limit | 30 cores |
| Memory | 140.9 GB / 259.8 GB (54%) — not pressured |
| Pod restarts | 0 — stable |
| Cross-cluster | Only &lt;cluster-name&gt; affected (92%); all others <20% |
| system.merges | 3 active merges on `tenant_b.event_result` (TTLDelete + rewrite + vertical) |
| **system.processes** | **3 concurrent `SELECT * FROM tenant_a.event_result WHERE eventId IN (...)` — each scanning ~700M rows, running ~50s** |
| **system.processes** | **2 INSERTs into `tenant_b.event_result` — 12 GB and 3.5 GB memory (hundreds of columns)** |
| **top -H** | **QueryPipelineEx: 14+ threads at 36-56% each ≈ 20+ cores (primary consumer)** |
| **top -H** | **MergeMutate: 5 threads at 48-76% each ≈ 3 cores (secondary)** |
| **top -H** | **Load average: 75.64 — far exceeding 30 cores, system overloaded** |

## Root Cause

**Query + merge superposition on `event_result` tables.** CPU breakdown:

| Component | Estimated CPU | % of limit | Role |
|-----------|--------------|------------|------|
| `SELECT * FROM tenant_a.event_result` full-table scans (x3) | ~20+ cores | ~67%+ | **Primary** |
| TTL/rewrite merges on `tenant_b.event_result` | ~3 cores | ~10% | Secondary |
| INSERTs + AsyncMetrics + other | ~4 cores | ~13% | Background |

The 3 SELECT queries are the smoking gun:
- `SELECT * FROM tenant_a.event_result WHERE eventId IN ('...')` — single eventId lookup
- Scanning **700M rows** per query → `eventId` is not in the primary key / ORDER BY prefix → **full-table scan**
- `SELECT *` on a table with **hundreds of columns** → reading massive amounts of data per row
- 3 concurrent queries → CPU superposition far exceeding what merges alone would cause

## Key Differentiator

| CPU scenario | system.merges | system.processes | top -H dominant |
|--------------|--------------|-----------------|-----------------|
| Pure merge debt | Heavy merges | No expensive queries | MergeMutate |
| **Query + merge superposition (this case)** | **Merges present** | **Expensive full-scan queries** | **QueryPipelineEx + MergeMutate** |
| Pure query overload | Normal or idle | Many expensive queries | QueryPipelineEx |

## Conclusion

The initial hypothesis of "merge debt" was **partially correct but incomplete**. Merges contribute ~10% CPU, but the dominant consumer (~67%+) is 3 concurrent full-table scan queries on `tenant_a.event_result`. Without `system.processes` and `top -H`, the merge-only conclusion would have been misleading.

## Verification

- After the 3 SELECT queries finish: CPU should drop significantly (from ~92% to ~30-40%)
- If CPU stays high after queries end but merges continue: then merge debt is the remaining contributor
- Check `system.query_log` for the frequency of these eventId lookups — if recurring, this is a systemic issue

## Recommended Action

**Short-term**:
- Identify the service/client issuing `SELECT * FROM tenant_a.event_result WHERE eventId IN (...)` queries
- Reduce per-query parallelism: set `max_threads` lower for this query profile
- Replace `SELECT *` with only the needed columns

**Long-term**:
- If `eventId` lookups are frequent: add a **projection** or **materialized view** with `eventId` as the ORDER BY prefix
- Alternatively, add a **bloom_filter skip index** on `eventId` to avoid full-table scans
- Review TTL settings on `tenant_b.event_result` to avoid long-running 54-85 GB single-partition rewrites during peak hours

## References

- `pattern-clickhouse-merge-cpu-root-cause.md` — merge debt model (applicable to secondary cause only)
- `card-clickhouse-merge-pressure-fast-signals.md` — fast triage card
- Investigation output: `tmp/sre-triage-<date>.md`
