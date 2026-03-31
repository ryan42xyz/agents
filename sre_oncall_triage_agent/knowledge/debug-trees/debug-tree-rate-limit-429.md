---
metadata:
  kind: debug-tree
  status: stable
  summary: "Diagnose ingress 429 rate limiting caused by burst traffic vs rate-limit window mismatch"
  tags: ["429", "rate-limit", "ingress", "burst", "window-mismatch"]
  first_action: "mcp__victoriametrics__query_range: sum(rate(kubernetes_monitoring_request_total_ingress_nginx{client='{client}', status_code='429'}[1m]))"
  routing_cluster: "Cluster 1 — Routing/Ingress"
  related:
    - patterns/pattern-ingress-rate-limit-429-window-mismatch.md
    - checklists/checklist-aws-lb-ingress-troubleshooting-checklist.md
---

# Debug Tree: Ingress Rate Limit 429 + Burst Window Mismatch

## Match Condition

- Customer reports intermittent failures
- 429 status codes observed in ingress metrics
- 1m average QPS appears healthy
- May be accompanied by traffic switch / recent config or restart

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| client | yes | triage extraction |
| cluster | yes | triage extraction or alert labels |
| namespace | recommended | usually ingress-nginx |
| time_window | yes | alert time or default now-2h→now |

## Steps

### Step 1: Confirm 429 presence and magnitude

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `sum(rate(kubernetes_monitoring_request_total_ingress_nginx{client="{client}", status_code="429"}[1m]))`
- **Time**: `start={time_window_start}`, `end={time_window_end}`, `step=1m`
- **Assess**: are 429s present? What's the rate relative to total traffic?
- **Branch**:
  - No 429s → FINDING: "No 429 observed in time window" → **MANUAL** (check other error codes)
  - 429 rate < 1% of total → FINDING: "Minimal 429, likely transient" → **CONCLUSION**: `MONITOR`
  - 429 rate significant → CONTINUE Step 2
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → FINDING: "no 429s detected in time window" (this is a valid finding, not an error)
  - metric not found → FALLBACK_QUERY (try `nginx_ingress_controller_requests{status="429"}`)
  - other → ESCALATE

### Step 2: Compare short-window vs long-window QPS

- **Tool**: `mcp__victoriametrics__query_range`
- **Queries** (run both):
  1. Long window: `sum(rate(kubernetes_monitoring_request_total_ingress_nginx{client="{client}", status_code="200"}[1m]))`
  2. Short window (if available): `sum(rate(kubernetes_monitoring_request_total_ingress_nginx{client="{client}", status_code="200"}[5s]))` or instant rate
- **Assess**: does 1m average look healthy while short-window shows bursts?
- **Branch**:
  - 1m healthy but short-window bursts visible → FINDING: "Burst + rate limit window mismatch" → CONTINUE Step 3
  - Both windows show sustained high QPS → FINDING: "Sustained high traffic triggering rate limit" → **ESCALATE** (capacity issue)
  - Short-window also smooth → FINDING: "No burst visible" → CONTINUE Step 3
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("QPS metric unavailable — cannot determine burst pattern")
  - metric not found → FALLBACK_QUERY (try alternative rate metric or Grafana dashboard query)
  - other → ESCALATE

### Step 3: Check ingress rate limit configuration

- **Tool**: kubectl (read-only, for checklist generation only — not auto-executed)
- **Command template**: `kubectl get ingress -A -o yaml | grep -E "global-rate-limit"`
- **What to look for**:
  - `global-rate-limit` annotation value
  - `global-rate-limit-window` value (1s vs 1m matters hugely)
  - Whether limit applies per-client or globally
- **Branch**:
  - Window is `1s` and bursts are sub-second → FINDING: "1s window causes false throttle on bursty traffic" → CONTINUE Step 4
  - Window is `1m` → FINDING: "1m window should absorb bursts — check if sustained QPS exceeds limit" → **MANUAL**
  - Config not found → FINDING: "Rate limit config not in ingress annotations" → **MANUAL** (check APISIX or other gateway)
- **on_error**:
  - kubectl failure → ESCALATE ("cannot read ingress config — cluster access issue")
  - other → ESCALATE

### Step 4: Correlate 429 spikes with traffic pattern

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: overlay 429 rate and total QPS on same time axis
  - `sum by (status_code) (rate(kubernetes_monitoring_request_total_ingress_nginx{client="{client}"}[1m]))`
- **Assess**: do 429 spikes align with QPS bursts?
- **Branch**:
  - Strong correlation (429 appears at traffic peaks) → **CONCLUSION**: `MONITOR` — burst traffic triggering rate limit; verify window config and consider widening
  - No correlation → FINDING: "429s not aligned with traffic peaks" → **ESCALATE** (possible misconfiguration)
  - 429 appears after traffic switch / restart → **ESCALATE** — possible config change impact
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("correlation query returned no data — conclude based on Steps 1-3")
  - other → ESCALATE

### Step 5: Check for recent changes (optional)

- Check for recent deployments, config changes, traffic switches
- **Tool**: Loki logs or deployment events
- **Branch**:
  - Recent change correlates with 429 onset → **ESCALATE** — change-related regression
  - No recent changes → FINDING: "No change event found" → conclude based on Step 4
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result / query failure → MARK_UNKNOWN ("optional step — conclude based on Step 4")
  - other → ESCALATE

## Resolution Template

```markdown
## Conclusion
- verdict: {MONITOR | ESCALATE | MANUAL}
- confidence: {high | medium | low}
- evidence_chain: [Step 1: 429 rate={val} → Step 2: burst mismatch={yes/no} → Step 3: window={val}]
- root_cause: {description}
- recommended_action:
  - MONITOR: verify short-window QPS↔429 correlation, check rate limit config/window
  - ESCALATE: confirm rate limit config change, assess customer impact scope
```

## Historical Cases (7 cases)

- **3 complete cases**: 1 escalate (customer-facing + config change), 2 monitor (verify burst↔429 correlation)
- **4 partial cases**: all B_potential_risk, hypothesis = burst window mismatch
- Common pattern: 1m QPS healthy but 1s/5s spikes trigger rate limiting
