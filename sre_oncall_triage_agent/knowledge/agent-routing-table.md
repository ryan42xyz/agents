---
metadata:
  kind: agent-routing-table
  status: v0.1-draft
  schema_version: "0.1"
  derived_from:
    - cases/case-monitoring-alert-delay-histogram-skew.trace.md
    - cases/case-clickhouse-connection-refused-troubleshooting.trace.md
    - cases/case-kafka-lag-issues.trace.md
---

# Agent Routing Table

> This is the orchestrator's first decision layer.
> Given an incoming alert signal, route to the correct cluster triage policy.
> Each cluster has its own decision trace and triage policy (see `.trace.md` files).

---

## Signal → Cluster Routing

| Signal Pattern | Key Discriminator | → Cluster | → Triage Policy |
|----------------|-------------------|-----------|-----------------|
| P99 latency high, error_rate normal | latency without errors = suspect observability | Cluster 4 — False signals | `histogram-skew-false-p99` |
| P99 latency high, error_rate elevated | real user impact | Cluster 1 or 3 | service-specific policy |
| connection refused (TCP) | "refused" = nothing listening | Cluster 1 — Routing/DNS/Ingress | `connection-refused-layered-triage` |
| connection timeout (TCP) | "timeout" = packet lost | Cluster 1 — Routing/LB/Network | `connection-timeout-routing-triage` (TBD) |
| kafka consumer lag, multi-topic same CG | systemic → check sink first | Cluster 3 — Stateful pressure | `kafka-lag-downstream-write-bottleneck` |
| kafka consumer lag, single topic/partition | isolated → check consumer/broker | Cluster 3 variant | `kafka-lag-consumer-partition-triage` (TBD) |
| pod Pending / FailedScheduling | can't place workload | Cluster 2 — Scheduling/Capacity | `pod-scheduling-failure-triage` (TBD) |
| pod Evicted / DiskPressure | node pressure | Cluster 2 — Node pressure | `node-disk-pressure-triage` (TBD) |
| AccessDenied / 403 / UnauthorizedOperation | identity/permissions | Cluster 5 — Identity/Access | `iam-access-denied-triage` (TBD) |
| post-upgrade regression | change management | Cluster 6 — Upgrades/Changes | `upgrade-regression-triage` (TBD) |

---

## Routing Decision Logic

```
STEP 1: classify error type
  IF connection_refused → Cluster 1, policy: connection-refused-layered-triage
  IF connection_timeout → Cluster 1, policy: timeout variant (TBD)

STEP 2: if latency alert
  IF error_rate == normal → Cluster 4, policy: histogram-skew-false-p99
  IF error_rate elevated  → route to service-specific investigation

STEP 3: if lag/throughput alert
  IF multi_topic, same_CG → Cluster 3, policy: kafka-lag-downstream-write-bottleneck
  IF single_topic         → Cluster 3 variant (TBD)

STEP 4: if scheduling/node alert
  IF pod_pending OR failed_scheduling → Cluster 2 (TBD)
  IF evicted OR disk_pressure         → Cluster 2 node variant (TBD)

STEP 5: if access/permission alert
  IF AccessDenied OR 403 → Cluster 5 (TBD)

STEP 6: if regression post-change
  IF correlates with recent deploy/upgrade → Cluster 6 (TBD)
```

---

## Key Discriminators (Cross-Cluster)

These are the signal pairs that most commonly cause misrouting:

| Pair | Discriminator | Wrong assumption |
|------|---------------|-----------------|
| refused vs timeout | refused = no listener; timeout = no route | Treating timeout as refused → wrong layer |
| P99 spike vs real latency | check error_rate + logs before trusting metric | Trusting P99 directly → false escalation |
| Kafka lag root cause | multi-topic = sink; single-topic = consumer/broker | Restarting broker when sink is broken |
| stateful "alive but not serving" | check state pressure, not just up/down | Declaring service down when it's backpressured |

---

## Cluster Coverage Status

| Cluster | Status | Trace File |
|---------|--------|------------|
| 1 — Routing / DNS / Ingress | DONE | `case-clickhouse-connection-refused-troubleshooting.trace.md` |
| 2 — Scheduling / Node Pressure | DONE | `cluster2-scheduling-node-pressure.trace.md` |
| 3 — Stateful Write Pressure | DONE | `case-kafka-lag-issues.trace.md` |
| 4 — Observability / False Signals | DONE | `case-monitoring-alert-delay-histogram-skew.trace.md` |
| 5 — Identity / Access Control | DONE | `cluster5-identity-access.trace.md` |
| 6 — Change Management / Upgrades | DONE | `cluster6-change-management.trace.md` |

---

## Invariants (Apply to All Clusters)

These rules apply regardless of which cluster the signal routes to:

1. **Read-only first**: all diagnostic steps are read-only until root cause is confirmed
2. **Human gate before action**: any state-changing action requires explicit approval
3. **Blast radius before fix**: always assess blast radius before applying mitigation
4. **Evidence chain required**: verifier must check evidence chain before closing
5. **Structural fix != mitigation**: short-term restart ≠ long-term fix; always file follow-ups
6. **Timeline correlation required**: causal claims must be supported by time-aligned evidence
