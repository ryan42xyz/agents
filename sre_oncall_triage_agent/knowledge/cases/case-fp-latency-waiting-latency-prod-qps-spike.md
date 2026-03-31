---
metadata:
  kind: case
  status: final
  summary: "Production serving API latency incident where ingress request_time rose while upstream_response_time stayed near baseline (waiting_latency dominated). Triggered by a single large tenant QPS spike in <prod-cluster-a>, saturating ingress connection/queue capacity before upstream. Mitigations focus on stopping the bleeding (tenant-aware limiting/degradation/traffic distribution) and restoring ingress headroom; verify by waiting_latency and p95/p99 recovery."
  tags: ["serving", "latency", "production", "ingress", "nginx", "waiting-latency", "qps-spike", "tenant", "k8s"]
  first_action: "Decompose ingress request_time vs upstream_response_time to confirm waiting_latency dominates (upstream normal)"
  related:
    - ./case-fp-latency-waiting-latency-prod-qps-spike.incident.md
    - ./pattern-fp-latency-waiting-latency-pattern.md
    - ./checklist-fp-latency-uswest-preprod-checklist.md
    - ./reference-latency-metrics-ingress-apisix.md
    - ./runbook-nginx-debugging-runbook.md
    - ./checklist-aws-lb-ingress-troubleshooting-checklist.md
    - ./reference-grafana-vmalert-aws-k8s-links.md
    - ./pattern-ingress-rate-limit-429-window-mismatch.md
    - ./case-large-tenant-qps-spike-joint-mitigation.md
    - ./card-fp-infra-fast-entrypoints.md
---

# Production Serving API High Latency: waiting_latency Dominates During Single-Tenant QPS Spike

## TL;DR (Do This First)
1. Confirm latency decomposition: ingress `request_time` high while `upstream_response_time` normal -> waiting_latency dominates.
2. Confirm it is a QPS spike and identify whether a single tenant dominates traffic.
3. Check ingress controller saturation signals (CPU/mem, connections, retries, 502/504).
4. Stop the bleeding: tenant-aware rate limit/degradation and/or distribute traffic (`#MANUAL`).
5. Restore headroom: scale ingress controller capacity (`#MANUAL`), then verify waiting_latency and p95/p99 recover.

## Safety Boundaries
- Read-only: dashboards/logs, `kubectl get/describe/logs/top`, time correlation.
- `#MANUAL`: rate limiting/degradation, traffic routing/splitting, scaling ingress controller replicas/resources, config changes.

## Related
- [case-fp-latency-waiting-latency-prod-qps-spike.incident.md](./case-fp-latency-waiting-latency-prod-qps-spike.incident.md)
- [pattern-fp-latency-waiting-latency-pattern.md](./pattern-fp-latency-waiting-latency-pattern.md)
- [checklist-fp-latency-uswest-preprod-checklist.md](./checklist-fp-latency-uswest-preprod-checklist.md) (method is reusable; substitute prod cluster/env)
- [./reference-latency-metrics-ingress-apisix.md](./reference-latency-metrics-ingress-apisix.md)
- [runbook-nginx-debugging-runbook.md](./runbook-nginx-debugging-runbook.md)
- [checklist-aws-lb-ingress-troubleshooting-checklist.md](./checklist-aws-lb-ingress-troubleshooting-checklist.md)
- [pattern-ingress-rate-limit-429-window-mismatch.md](./pattern-ingress-rate-limit-429-window-mismatch.md)
- [case-large-tenant-qps-spike-joint-mitigation.md](./case-large-tenant-qps-spike-joint-mitigation.md) (QPS spike mitigation patterns)

## One-line Essence
> Upstream is fine; ingress is waiting/queueing (waiting_latency) under sudden QPS spike, often dominated by one tenant.

## Context
- Cluster: `<prod-cluster-a>`
- Service: Serving API behind ingress-nginx

## Trigger / Symptoms (Production Story)
- Alert: serving API latency p95/p99 sustained high for > 10 minutes.
- Observations (same time window):
  - Ingress `request_time` p95/p99 high.
  - `upstream_response_time` stays near baseline.
  - Therefore `waiting_latency = request_time - upstream_response_time` dominates.
  - QPS spikes sharply and is dominated by a single tenant.

## Triage

### 1) Prove it is waiting_latency (not upstream)
- If `request_time` high but `upstream_response_time` normal: classify as waiting_latency dominant.
- Prioritize ingress/connection/scheduling layers first; do not start with application business logic.

### 2) Confirm the spike is tenant-dominant
- In access logs or dashboards, identify whether a single tenant/client dominates:
  - per-tenant QPS
  - top paths/endpoints
  - error rate and retry hints

### 3) Inspect ingress saturation signals
Read-only commands (examples):

```bash
kubectl get pods -n ingress-nginx -o wide
kubectl top pods -n ingress-nginx
kubectl describe pod -n ingress-nginx <ingress-controller-pod>
kubectl logs -n ingress-nginx <ingress-controller-pod> --tail=200
```

Signals that match this case:
- High connections / queueing symptoms and elevated waiting_latency.
- Rising 502/504 or upstream timeout messages while upstream latency stays normal.
- CPU throttling or memory pressure on ingress controller pods.

### 4) Differential diagnosis guardrails
- If upstream_response_time also rises: this is no longer a pure waiting_latency case; treat as upstream or downstream dependency bottleneck.
- If only one ingress pod/node is abnormal: suspect node-local networking/conntrack/DNS issues.

## Mitigation (Typical Production Moves)

### Stop the bleeding (preferred order)
- `#MANUAL` Tenant-aware rate limiting or temporary degradation for the hot tenant/path.
- `#MANUAL` If the system supports it, distribute load (traffic split / move some traffic to another cluster) to reduce peak pressure.

### Restore ingress headroom
- `#MANUAL` Scale ingress controller replicas and/or resources.
- Re-check waiting_latency within minutes; keep changes minimal and reversible.

## Verification
- waiting_latency drops (request_time approaches upstream_response_time again).
- p95/p99 latency returns to baseline and stays stable for 15-30 minutes.
- Error rate does not increase; 502/504 and retries stop worsening.

Recommended production thresholds:
- Decomposition recovery: `waiting_latency_p99 <= <baseline_waiting_p99> * (1 + <tolerance_percent>%)` for `>= 15m`
- User-facing recovery: serving p99 `<= <baseline_p99> * (1 + <tolerance_percent>%)` for `>= 15m`
- Safety: after any `#MANUAL` action, watch for regression for `>= 30m` (p99 + error rate)

## Closeout
- Record: time window, the tenant/path that dominated traffic, and the decomposition evidence.
- Record every `#MANUAL` action with who/when/why and rollback criteria.
- Follow-ups:
  - tenant-aware safeguards (quotas/rate limits)
  - ingress saturation leading indicators (connections/queue/retry)
  - a documented "waiting_latency dominant" first-branch playbook (this case + linked pattern/checklist)

Closeout checklist (production):
- Evidence snapshot: (a) request_time vs upstream_response_time before/peak/after, (b) tenant dominance (top tenant share), (c) ingress saturation signal(s).
- For each `#MANUAL` action: record `time/owner/change/rollback/result`.
- Rollback rules:
  - Tenant rate limit/degrade: step down gradually after 30m stable; revert immediately if false-positive blocks legitimate traffic.
  - Ingress scale: revert to baseline only after spike ends + 24h stable; monitor for cold-start regressions.
