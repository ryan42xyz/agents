---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-fp-latency-waiting-latency-prod-qps-spike.md
  title: "Production Serving API High Latency (waiting_latency Dominates) - Single Tenant QPS Spike"
  summary: "Production serving API latency alert where ingress request_time rose while upstream_response_time stayed near baseline (waiting_latency dominated). In <prod-cluster-a>, a single large tenant QPS spike saturated ingress capacity (connections/queueing) before upstream. Mitigation stopped the bleeding with tenant-aware limiting/degradation and restored ingress headroom by scaling controller capacity; verification based on waiting_latency and p95/p99 recovery."
  tags: [fp, latency, ingress, nginx, waiting-latency, production, qps-spike, tenant, kubernetes]
  patterns: [fp-latency-waiting-latency-ingress-saturation]
---

# Incident: Production Serving API High Latency (waiting_latency Dominates) - Single Tenant QPS Spike

## 1. Incident Overview
- Date: <YYYY-MM-DD> (local time <TZ>)
- Severity: <SEV-1|SEV-2> (based on p99 + error impact)
- Duration: <~minutes> (from alert to stable recovery window)
- System: Client -> LB -> ingress-nginx -> serving API
- Impact: elevated p95/p99 latency on serving APIs; tenant-dominant traffic caused partial degradation

## 2. System Context
- Latency decomposition model:
  - `waiting_latency = request_time - upstream_response_time`
- When waiting_latency dominates, the primary suspects are ingress/connection/queueing layers rather than upstream processing.

## 3. Environment
- Environment: production
- Cluster: `<prod-cluster-a>`
- Platform: Kubernetes
- Entry: ingress-nginx
- Service: serving API

## 4. Trigger
- Trigger: sustained serving latency alert (p95/p99) for > 10 minutes.

## 5. Impact Analysis
- Blast radius: <single-cluster|multi-cluster> (serving behind ingress in <prod-cluster-a>)
- Error rate: <baseline_%> -> <peak_%> -> <recovered_%>
- SLO/SLA breach: <yes/no> (p99 exceeded <threshold_ms> for <minutes>)
- Primary customer impact: dominated by one tenant; others experienced <low/medium> collateral impact
- Key metrics (sanitized before/peak/after):
  - ingress request_time p99: <baseline_ms> -> <peak_ms> -> <recovered_ms>
  - ingress upstream_response_time p99: <baseline_ms> -> <peak_ms> -> <recovered_ms>
  - waiting_latency p99: <baseline_ms> -> <peak_ms> -> <recovered_ms>

## 6. Constraints
- High blast-radius actions require explicit ownership/approval:
  - tenant-aware rate limiting/degradation
  - traffic routing/splitting
  - scaling ingress controller and config changes

## 7. Investigation Timeline
- T0: latency alert fired (time window <start>-<end>)
- T0+X: decomposition showed waiting_latency dominant (upstream normal)
- T0+Y: QPS spike confirmed; traffic dominated by a single tenant
- T0+Z: ingress saturation signals observed (connections/queueing/retries)
- T0+Z+N: mitigation applied (tenant limiting/degradation; ingress scaled)
- T0+Z+M: verification completed (waiting_latency and p95/p99 recovered)

Timeline (sanitized; replace placeholders with actual timestamps when available):
- T0: alert fired.
- T0+<m>: confirmed waiting_latency dominance (request_time high; upstream_response_time near baseline).
- T0+<m>: confirmed tenant dominance (top tenant share <a%> -> <b%>; hottest path `<path>`).
- T0+<m>: ingress saturation evidence collected (choose 2-3):
  - connections/queueing elevated
  - 502/504 rising
  - CPU throttling / memory pressure
- T0+<m> `#MANUAL`: applied tenant rate limit/degradation (rollback: staged rollback after stability).
- T0+<m> `#MANUAL`: scaled ingress controller replicas/resources (rollback: revert after spike ends + 24h stable).
- T0+<m>: verification: waiting_latency dropped and p99 stabilized for >= 15m.

## 8. Root Cause
- Root cause: a single tenant QPS spike saturated ingress capacity (connections/queueing), introducing waiting before upstream.
- Symptom vs root cause:
  - Symptom: high request_time / high p95/p99
  - Root cause: ingress waiting/queueing (waiting_latency) under sudden tenant-dominant load

## 9. Mitigation
- `#MANUAL`: stop the bleeding with tenant-aware rate limiting and/or temporary degradation.
- `#MANUAL`: restore headroom by scaling ingress controller replicas/resources.
- Optional (if supported): distribute load by traffic splitting/routing to reduce peak concentration.

Action log (production-grade; sanitized):
- `#MANUAL` <time> <owner>: applied tenant rate-limit/degradation for `<tenant>`/`<path>`. Rollback: step down after 30m stable; immediate rollback if false-positive.
- `#MANUAL` <time> <owner>: scaled ingress controller from <n> -> <m> replicas (or resources). Rollback: revert after spike ends + 24h stable.

## 10. Prevention / Improvement
- Tenant-aware safeguards:
  - enforce quotas/rate limits for top tenants
  - detect tenant dominance early (top-N tenant QPS alert)
- Ingress leading indicators:
  - connections/queue/retry/timeout SLOs aligned with waiting_latency
- Change playbook:
  - standard first branch for latency incidents: decompose waiting_latency vs upstream

## 11. Generalizable Lessons
- When upstream is normal, do not deep-dive application business logic first.
- QPS spikes often manifest as waiting_latency at the edge before upstream slows.
- Stopping the bleeding (limit/degrade/distribute) is usually faster than scaling everything blindly.

## Verification (Production Gate)
- waiting_latency p99 returns within <tolerance_percent>% of baseline for >= 15m
- serving p99 returns within <tolerance_percent>% of baseline for >= 15m
- error rate returns within <delta>% of baseline for >= 15m

## Evidence Mapping
- Decomposition evidence -> `case-fp-latency-waiting-latency-prod-qps-spike.md` (Trigger / Symptoms)
- Tenant dominance evidence -> `case-fp-latency-waiting-latency-prod-qps-spike.md` (Triage: Confirm the spike is tenant-dominant)
- Ingress saturation signals -> `case-fp-latency-waiting-latency-prod-qps-spike.md` (Triage: Inspect ingress saturation signals)
- Mitigation actions -> `case-fp-latency-waiting-latency-prod-qps-spike.md` (Mitigation)
- Verification -> `case-fp-latency-waiting-latency-prod-qps-spike.md` (Verification)
