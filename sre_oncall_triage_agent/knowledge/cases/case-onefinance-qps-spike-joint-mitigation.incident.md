---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-large-tenant-qps-spike-joint-mitigation.md
  title: "Large-Tenant QPS Spike (Joint Mitigation: Rate Limit + Scale + Traffic Split)"
  summary: "EN: Traffic spike incident response across serving + async + storage: split traffic 50/50, scale serving/async within guardrails, increase Kafka partitions, vertically scale the DB, and disable non-critical recompute/backfill via dynamic TenantInfo rate limits to protect the critical path."
  tags: [incident, qps-spike, rate-limit, scaling, kafka, db, k8s]
  patterns: [traffic-spike-critical-path-degradation]
---

# Incident: Large-Tenant QPS Spike (Joint Mitigation: Rate Limit + Scale + Traffic Split)

## 1. Incident Overview
- Date: <YYYY-MM-DD> (local time <TZ>)
- Severity: <SEV-1|SEV-2>
- Duration: <~minutes> (from alert to stable recovery window)
- System: client -> traffic switch -> gateway -> serving -> async consumer -> Kafka -> DB
- Impact: multi-layer saturation; serving latency rose and error rate risk increased during spike (quantified below)

## 2. System Context
- Critical path: real-time requests (serving)
- Non-critical work: recompute / agg backfill background tasks (deferable)
- Key coupling: async workload competes for CPU/IO and downstream DB capacity

## 3. Environment
- Platform: Kubernetes (pods/HPA mentioned)
- Gateway: gateway
- Streaming: Kafka
- Database: DB
- Dynamic config: TenantInfo parameters (no restart)

## 4. Incident Trigger
- Trigger: large-tenant QPS spike (upstream driver <known/unknown>)

## 5. Impact Analysis
- Blast radius: pipeline-wide (serving + async + DB)
- Data loss: none observed / not indicated
- SLO/SLA breach: <yes/no> (p99 exceeded <threshold_ms> for <minutes>)
- Key metrics (sanitized before/peak/after):
  - serving p99: <baseline_ms> -> <peak_ms> -> <recovered_ms>
  - serving error rate: <baseline_%> -> <peak_%> -> <recovered_%>
  - async backlog/lag: <baseline> -> <peak> -> <trend_down_yes/no>
  - DB saturation: <baseline> -> <peak> -> <recovered>

## 6. Constraints
- Scaling must be bounded to avoid crushing the database.
- Prefer dynamic config toggles over restarts during incident.

## 7. Investigation Timeline
Timeline (sanitized; fill in exact times from alert window):
- T0: alert fired for serving latency and/or error rate.
- T0+<m>: confirmed tenant dominance (top tenant share <a%> -> <b%>; top path `<path>`).
- T0+<m>: classified bottlenecks (serving saturation + async backlog + DB pressure).
- T0+<m> `#MANUAL` traffic: applied 50/50 split (rollback: revert after 30m stable KPIs).
- T0+<m> `#MANUAL` degradation: set TenantInfo background limits to 0 (rollback: step up gradually after stability).
- T0+<m> `#MANUAL` scaling: bounded scale serving/async (caps preserved; rollback: restore baseline HPA after spike).
- T0+<m> `#MANUAL` Kafka: increased partitions for tenant-scoped topics (documented; no rollback during incident).
- T0+<m> `#MANUAL` DB: vertical scale to restore headroom (rollback plan: revert after spike ends + 24h stable).
- T0+<m>: verification: p99/error recovered and remained stable for >= 15m; lag slope decreased.

## 8. Root Cause
- Root cause: sudden external traffic spike exceeded pre-spike capacity across multiple coupled components.
- Contributing factor: non-critical background workloads competed with critical path during spike.

Evidence summary (sanitized):
- Tenant dominance: top tenant traffic share increased sharply during incident window.
- Serving saturation: latency increased under spike; edge/ingress saturation signals present.
- Downstream pressure: async backlog increased and DB pressure signals correlated with serving degradation.

## 9. Resolution
- Mitigation actions documented:
  - Split 50/50 traffic
  - Tune consumer thread pool sizes
  - Adjust HPA bounds
  - Double Kafka partitions for specific topics
  - Vertically scale the DB
  - Disable recompute and agg backfill via TenantInfo
- Verification (production gate):
  - serving p95/p99 within <tolerance_percent>% of baseline for >= 15m
  - error rate within <delta>% of baseline for >= 15m
  - async lag/backlog slope decreasing for >= 10m
  - DB pressure stabilized (no new timeouts; latency trending down) for >= 15m

## 10. Prevention / Improvement
- Codify a surge playbook: traffic split -> bounded scale -> pause non-critical -> infra scale.
- Make background jobs explicitly preemptible with safe ramp-down/ramp-up procedures.
- Load test spike scenarios; define max safe HPA and DB headroom.
- Add first-class observability on recompute lag/backlog, DB saturation, consumer throughput.

## 11. Generalizable Lessons
- Prefer deliberate degradation: trade data freshness for uptime by pausing non-critical work.
- Scaling without guardrails can worsen downstream overload; confirm DB headroom.
- Traffic splitting buys time; pair with workload shaping to stop recurrence.
- Pattern Card:
  - Pattern name: traffic-spike-critical-path-degradation
  - When it happens: QPS spikes saturate multiple layers
  - Fast detection signals: rising latency/queue lag + DB saturation
  - Fast mitigation: split traffic + pause background work + bounded scaling
- Common pitfalls: unbounded scale; restarting blindly; leaving background tasks on

## Tags & Patterns
- Tags: incident, qps-spike, rate-limit, scaling, kafka, db, k8s
- Patterns: traffic-spike-critical-path-degradation
- First Action: confirm spike + identify critical path vs deferable workloads

## Evidence Mapping
- Trigger -> "Confirm this is a QPS spike impacting a large tenant" (case-large-tenant-qps-spike-joint-mitigation.md:TL;DR)
- Bottleneck -> "protect the realtime critical path first (serving API)" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Bottleneck -> "Confirm the DB is the bottleneck" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Traffic mitigation -> "Split 50/50 traffic" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- HPA bounds -> "serving hpa: min <min>, max <max>" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- HPA bounds -> "async-consumer hpa: min <min>, max <max>" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Thread pool -> "COREPOOLSIZEINCONSUMER = 40" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Thread pool -> "MAXPOOLSIZEINCONSUMER = 80" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Kafka -> "Double partitions for the incident topics" (case-large-tenant-qps-spike-joint-mitigation.md:Triage)
- Degradation -> "hotspotRecomputeTaskRateLimitPerPartition = 0" (case-large-tenant-qps-spike-joint-mitigation.md:TL;DR)
- Degradation -> "hotspotAggBackfillTaskRateLimitPerPartition = 0" (case-large-tenant-qps-spike-joint-mitigation.md:TL;DR)
