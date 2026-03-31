---
metadata:
  kind: structured-triage-trace
  status: final
  source: case-monitoring-alert-delay-histogram-skew.incident.md
  schema_version: "0.1"
  tags: ["monitoring", "prometheus", "histogram", "p99", "false-alert"]
  failure_domain: "observability / false signals"
  cluster: "Cluster 4 — Metrics interpretation, false signals"
---

# Structured Triage Trace: Histogram Skew Inflated P99

> This artifact transforms a human-narrative incident case into a machine-consumable
> decision trace. It is designed for use as: (1) an agent triage exemplar,
> (2) a verifier checklist, and (3) a policy extraction substrate.

---

## Signal

```
alert:     Prometheus P99 latency high (~6s)
signal:    P99 spike — no correlated error rate change
→ cluster: Cluster 4 (Observability / False Signals)
→ reason:  P99 spike without error_rate elevation is the canonical
           false-signal signature in this cluster
```

### Routing Logic

```
IF   alert_type == latency_high
AND  error_rate == normal
THEN suspect_false_signal = true
     → route to Cluster 4 triage path
     → first_action: disprove real latency before investigating metrics
```

---

## Decision Trace

Each row is one worker step: what was queried, what was observed, what was inferred,
and the confidence level going into the next step.

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Check error rate in same time window | PromQL / Grafana | Error rate: normal, no elevation | P99 spike without errors → probably not real user impact | 0.75 |
| 2 | Check application logs in same window | App logs / APM | No slow requests, no timeout entries | User-visible latency not real | 0.85 |
| 3 | Compare P99 per instance | PromQL per-instance histogram | Instances diverged sharply for a short window | Not a real slowdown — divergence is aggregation artifact | 0.90 |
| 4 | Check scrape timestamp alignment | vmagent scrape metadata | Scrape timing misaligned across instances | Bucket counts from different time slices aggregated together | 0.90 |
| 5 | Verify alerting pipeline state | Rule engine API (`/api/v1/rules`) | Alert was `pending` in rule engine, not `firing` | Slack showed historical message — not current firing | 0.95 |
| 6 | Cross-check Alertmanager | Alertmanager `/api/v1/alerts` | No currently firing alerts | Confirms: incident is observability artifact, not real | 0.98 |

---

## Evidence Chain

```
root_cause_1: scrape_time_misalignment
  mechanism:  vmagent did not scrape all instances at the same wall-clock time
  evidence:   step 4 — scrape timestamp delta observed across instances

root_cause_2: histogram_bucket_aggregation_skew
  mechanism:  when buckets from misaligned scrapes are summed, the synthetic
              P99 is calculated over an inconsistent denominator, inflating the tail
  evidence:   step 3 — per-instance P99 divergence only in short window

false_positive_confirmed_by:
  - step 1: no error_rate elevation
  - step 2: no slow requests in app logs / APM
  - step 5: alert state was `pending` not `firing`
  - step 6: Alertmanager shows no active alert

ruled_out:
  - real user latency spike (step 2: logs/APM clean)
  - upstream service degradation (step 2: no correlated errors)
  - application regression (step 1: error rate unchanged)
```

---

## Triage Policy (Extracted)

This is the reusable policy for future agent triage of the same failure pattern.

```yaml
policy_name: histogram-skew-false-p99

trigger:
  alert: latency_p99_high
  condition: error_rate == normal

steps:
  - id: step_1
    action: query_error_rate
    tool: prometheus
    query: "rate(http_errors_total[5m])"
    gate: IF elevated → exit to real-latency triage path
    on_normal: continue

  - id: step_2
    action: check_app_logs_apm
    tool: loki_or_apm
    query: "errors OR slow_requests in same time window"
    gate: IF slow_requests found → exit to real-latency triage path
    on_clean: continue

  - id: step_3
    action: compare_per_instance_histogram
    tool: prometheus
    query: "histogram_quantile(0.99, ...) by (instance)"
    gate: IF all instances aligned → not histogram skew, escalate
    on_diverged: continue

  - id: step_4
    action: check_scrape_alignment
    tool: prometheus_metadata
    signal: scrape_timestamp delta across instances
    gate: IF aligned → not scrape skew, escalate
    on_misaligned: root_cause = histogram_skew_confirmed

  - id: step_5
    action: verify_alert_engine_state
    tool: rule_engine_api
    endpoint: /api/v1/rules
    gate: IF firing → real alert, escalate
    on_pending_or_inactive: false_alert_likely

  - id: step_6
    action: verify_alertmanager_state
    tool: alertmanager_api
    endpoint: /api/v1/alerts
    gate: IF active alerts exist → escalate
    on_empty: false_alert_confirmed

verdict:
  false_alert: close with template
  real_latency: escalate to service owner

human_gates:
  - before: any rule/scrape config change (#MANUAL)
  - before: any rollout restart of vmagent/vmalert
```

---

## Verifier Checklist

Before the agent closes this as a false alert, all of the following must pass:

- [ ] Error rate was not elevated in the same time window
- [ ] App logs / APM show no slow requests in the same time window
- [ ] Per-instance P99 shows divergence (not uniform elevation)
- [ ] Scrape timestamps show misalignment across instances
- [ ] Rule engine state is `pending` or `inactive`, not `firing`
- [ ] Alertmanager `/api/v1/alerts` shows no active alert for this rule

If any item fails → escalate, do not close as false alert.

---

## Blast Radius

```
action_surface:  read-only (queries, log inspection, API checks)
human_gate:      required before any config change or rollout restart
rollback_path:   N/A for read-only triage
escalation:      if checklist fails → page service owner
```

---

## Closeout Artifact

```
Status: FALSE ALERT

Root cause: scrape time misalignment + histogram bucket aggregation skew
User impact: none confirmed (logs/APM clean, error rate normal)
Alert state: was pending in rule engine, not actively firing

Evidence:
  - App logs: no slow requests in window
  - Per-instance histogram: short-window divergence only
  - Rule engine: alert state = pending
  - Alertmanager: no active firing alert

Follow-up items:
  - [ ] Align scrape intervals across instances
  - [ ] Add `for: 2m` to reduce paging on transient skew
  - [ ] Consider recording rule for P99 series stabilization
```

---

## Pattern Cross-Reference

```
pattern_name:     histogram-skew-false-p99
related_pattern:  alerting-pipeline-misattribution

key_principle:
  "Prove real user impact first (logs/APM + error rate).
   Only then investigate the metric signal.
   The signal is the last thing to trust, not the first."

cluster_rule:
  "In Cluster 4, the first question is always:
   is this observability noise or real user experience?"
```
