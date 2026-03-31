---
metadata:
  kind: debug-tree
  status: stable
  summary: "False P99 latency alert: histogram bucket skew + scrape misalignment causing phantom spikes"
  tags: ["monitoring", "prometheus", "histogram", "p99", "false-alert", "skew"]
  first_action: "Check error_rate alongside P99 — if error_rate normal, suspect false signal"
  routing_cluster: "Cluster 4 — Observability/False Signals"
  related:
    - cases/case-monitoring-alert-delay-histogram-skew.md
    - patterns/pattern-fp-latency-waiting-latency-pattern.md
    - references/reference-monitoring-system-k8s-overview.md
---

# Debug Tree: False P99 Latency Alert (Histogram Skew + Scrape Misalignment)

## Match Condition

- P99 latency alert fires or is pending (value appears elevated, e.g. ~6s)
- Error rate is **not** elevated in the same time window
- No user-visible slow requests in application logs or APM
- Spike is short-lived and does not persist across evaluation cycles

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| service | yes | alert labels or triage extraction |
| namespace | yes | alert labels or triage extraction |
| alert_name | yes | the alerting rule name (e.g. `HighP99Latency`) |
| histogram_metric | yes | the histogram metric used in the alert (e.g. `http_request_duration_seconds_bucket`) |
| job | recommended | Prometheus job label for the scraped target |
| cluster | recommended | Kubernetes cluster name if multi-cluster |

## Steps

### Step 1: Check error rate in the same time window

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `sum(rate(http_errors_total{namespace="{namespace}", job="{job}"}[5m])) / sum(rate(http_requests_total{namespace="{namespace}", job="{job}"}[5m]))`
- **Params**: `start=now-1h`, `end=now`, `step=1m`
- **Assess**: is error rate elevated above baseline?
- **Branch**:
  - Error rate elevated (> baseline + 2x stddev) -> FINDING: "Error rate elevated — likely real latency issue" -> **ESCALATE** to real-latency triage path
  - Error rate normal -> CONTINUE Step 2 (confidence: 0.75 that this is a false signal)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result / metric not found → ESCALATE (cannot determine if latency is real without error rate)
  - other → ESCALATE

### Step 2: Check application logs for slow requests

- **Tool**: `mcp__grafana__query_loki_logs`
- **Query**: `{namespace="{namespace}", job="{job}"} |= "slow" or "timeout" or "deadline exceeded" | logfmt | duration > 3s`
- **Params**: `start=now-1h`, `end=now`, `limit=50`
- **Assess**: are there actual slow requests or timeout entries in the logs?
- **Branch**:
  - Slow requests found -> FINDING: "Application logs confirm real slow requests" -> **ESCALATE** to real-latency triage path
  - Logs clean (no slow requests, no timeouts) -> CONTINUE Step 3 (confidence: 0.85 that P99 is false signal)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (Loki may not have logs for this service; continue investigation)
  - other → ESCALATE

### Step 3: Compare P99 per instance

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `histogram_quantile(0.99, sum by (instance, le) (rate({histogram_metric}{namespace="{namespace}", job="{job}"}[5m])))`
- **Params**: `start=now-1h`, `end=now`, `step=1m`
- **Assess**: do all instances show uniform P99 elevation, or do they diverge sharply in a short window?
- **Branch**:
  - All instances uniformly elevated -> FINDING: "P99 uniformly high across instances — not a skew artifact" -> **ESCALATE** (real latency or upstream issue)
  - Instances diverge sharply for a short window, then reconverge -> CONTINUE Step 4 (confidence: 0.90 — divergence is aggregation artifact)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (histogram metric may not exist for this service; skip to Step 5)
  - other → ESCALATE

### Step 4: Check scrape timestamp alignment

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `scrape_duration_seconds{namespace="{namespace}", job="{job}"}`
- **Params**: `start=now-30m`, `end=now`, `step=15s`
- **Also query**: `up{namespace="{namespace}", job="{job}"}` to see per-instance scrape timing
- **Tool (alternative)**: `mcp__victoriametrics__query`
- **Query**: `scrape_samples_scraped{namespace="{namespace}", job="{job}"}` — check if sample counts vary across instances
- **Assess**: are scrape timestamps aligned across instances, or is there significant drift?
- **Branch**:
  - Scrape timestamps aligned (delta < 2s across instances) -> FINDING: "Scrapes aligned — skew not from scrape misalignment" -> **ESCALATE** (investigate other histogram artifacts)
  - Scrape timestamps misaligned (delta > scrape_interval/2) -> ROOT CAUSE CONFIRMED: histogram skew from scrape misalignment -> CONTINUE Step 5 (confidence: 0.90)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (scrape metadata unavailable; continue to Step 5 without scrape alignment conclusion)
  - other → ESCALATE

### Step 5: Verify alert state in rule engine

- **Tool**: `mcp__victoriametrics__rules`
- **Query**: `rule_names=["{alert_name}"]`, `type="alert"`
- **Extract**: `state` (inactive / pending / firing), `health`, `lastError`
- **Branch**:
  - State is `firing` -> FINDING: "Alert currently firing — treat as real until disproven by all other steps" -> **ESCALATE**
  - State is `pending` or `inactive` -> CONTINUE Step 6 (confidence: 0.95 — Slack notification was historical, not current)
  - Rule not found -> FINDING: "Alert rule not found in vmalert" -> **MANUAL** (check rule config)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (rules API may be unavailable; continue to Step 6)
  - other → ESCALATE

### Step 6: Cross-check Alertmanager for active alerts

- **Tool**: `mcp__victoriametrics__alerts`
- **Assess**: is there a currently active/firing alert matching `{alert_name}`?
- **Branch**:
  - Active alert exists for this rule -> FINDING: "Alertmanager shows active alert — do not close" -> **ESCALATE**
  - No active alert -> FALSE ALERT CONFIRMED (confidence: 0.98) -> proceed to Resolution
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (alerts API may be unavailable; conclude based on prior steps)
  - other → ESCALATE

## Resolution Template

```markdown
## Conclusion
- verdict: FALSE_ALERT
- confidence: high
- evidence_chain: [Step 1: error rate normal -> Step 2: logs clean -> Step 3: per-instance P99 divergence -> Step 4: scrape misalignment confirmed -> Step 5: alert state pending/inactive -> Step 6: no active alert in Alertmanager]
- root_cause: Scrape time misalignment across instances caused histogram bucket counts from different time slices to be aggregated together, inflating the synthetic P99 calculation
- user_impact: none confirmed (application logs/APM clean, error rate normal)
- recommended_action:
  - (#MANUAL) Align scrape intervals across instances (ensure all targets in the same job use identical `scrape_interval`)
  - (#MANUAL) Add `for: 2m` to the alert rule to suppress transient skew spikes
  - (#MANUAL) Consider a recording rule to pre-aggregate P99 per-instance before cross-instance aggregation
- closeout_message: |
    Confirmed false alert.
    No real latency observed in application logs/APM in the same time window.
    Metric skew (scrape misalignment + histogram aggregation sensitivity) inflated P99.
    No production impact.
```

## Historical Cases

- **Histogram skew inflated P99 (case-monitoring-alert-delay-histogram-skew)**: P99 spiked to ~6s, error rate normal, app logs clean. Per-instance histograms diverged in short window. Scrape misalignment confirmed. Alert was `pending` not `firing`; Slack showed historical message. Verdict: FALSE_ALERT. Follow-ups: align scrape intervals, add `for: 2m`, consider recording rule.
