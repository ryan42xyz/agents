---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-monitoring-alert-delay-histogram-skew.md
  title: "Monitoring Alert Delay Misinterpretation plus Inflated P99 (Histogram Skew)"
  summary: "An oncall note about apparent ""alert delay"" and an inflated P99: first use logs/APM plus error rate to disprove real latency, then confirm per-instance histogram divergence; the root cause was scrape misalignment plus histogram bucket aggregation skew; also clarifies the alerting pipeline model (rule engine vs Alertmanager)."
  tags: [monitoring, alerting, prometheus, vmalert, alertmanager, histogram, p99]
  patterns: [histogram-skew-false-p99, alerting-pipeline-misattribution]
---

# Incident: Monitoring Alert Delay Misinterpretation plus Inflated P99

## 1. Incident Overview
- Date: TBD
- Severity: TBD
- Duration: TBD
- System: metrics plus rule engine (prom/vmalert) plus Alertmanager notification pipeline
- Impact: false latency alert (logs show no real slowdown) plus misinterpretation of notification timing/state

## 2. System Context
 - Alerting pipeline model (key separation):
  - rule engine decides pending/firing/resolved
  - Alertmanager groups/routes/sends
- Percentile signal chain: multi-instance histogram -> scrape -> aggregation -> P99

## 3. Environment
- Metrics storage: Prometheus / VictoriaMetrics (both referenced as concepts)
- Rule engine: Prometheus rule / vmalert
- Dispatcher: Alertmanager
- Notification: Slack/Email/Pager (conceptual)

## 4. Trigger
- Trigger: P99 latency high (example: `Prometheus P99 ~ 6s`)
- Additional concern: alert delay / Slack shows historical firing vs current state

## 5. Impact Analysis
- User-visible latency: not observed in logs
- Blast radius: alert correctness + oncall confidence
- Data loss: none indicated

## 6. Constraints
- Need to decide quickly: real latency vs observability artifact
- Rule/receiver changes are high-blast-radius and typically `#MANUAL`/reviewed (process: TBD)

## 7. Investigation Timeline
- Prove/disprove real latency: check app logs/APM in the same window.
- Check error rate correlation.
- Compare per-instance buckets/latency; divergence indicates skew.
- Attribute root cause: scrape timing misalignment + histogram aggregation distortion inflates P99.
- Clarify alert state:
  - rule engine APIs show current state
  - Alertmanager UI/API shows currently firing alerts

## 8. Root Cause
- Root cause (false P99): scrape time misalignment + histogram bucket aggregation skew.
- Root cause (alert delay confusion): mixing rule firing state with notification delivery/historical messages.

## 9. Mitigation
- Immediate: classify as false alert if logs + error rate are normal and skew explains P99.
- Communication: use the Slack template provided in the note.
- Config changes applied: TBD (note lists improvements; application not recorded).

## 10. Prevention / Improvement
- Align scrape intervals; avoid instance-level bucket sum without guarantees.
- Add `for:` to reduce paging on transient skew.
- Use recording rules to stabilize series then compute P99.
- Teach/encode the pipeline model in runbooks: rule vs alertmanager responsibilities.

## 11. Generalizable Lessons
- Separate "alert exists" (rule engine) from "alert delivered" (Alertmanager queue/grouping).
- Percentiles are extremely sensitive to skew; always corroborate with logs/APM.
- Pattern Card:
  - Pattern name: alerting-pipeline-misattribution
  - When it happens: oncall interprets Slack/history as current firing state
  - Fast detection signals: Alertmanager UI shows no firing while messages exist
  - Fast mitigation: check rule engine state and Alertmanager `/api/v1/alerts`
- Common pitfalls: changing rules while the issue is data skew

## Tags & Patterns
- Tags: monitoring, alerting, prometheus, vmalert, alertmanager, histogram, p99
- Patterns: histogram-skew-false-p99, alerting-pipeline-misattribution
- First Action: before trusting P99, use logs/APM to validate real user latency

## Evidence Mapping
- Triage -> "Prove/Disprove real user latency: check app logs/APM in the same time window" (case-monitoring-alert-delay-histogram-skew.md:TL;DR)
- Triage -> "Check error rate: if not elevated, suspect false alert" (case-monitoring-alert-delay-histogram-skew.md:TL;DR)
- Triage -> "Compare per-instance buckets/latency: divergence strongly indicates metrics skew" (case-monitoring-alert-delay-histogram-skew.md:TL;DR)
- One-line Essence -> "Scrape time misalignment -> P99 calculation inflated -> false alert (not real user latency)" (case-monitoring-alert-delay-histogram-skew.md:One-line Essence)
- Signal -> "Prometheus P99 ~ 6s" (case-monitoring-alert-delay-histogram-skew.md:Event Logic Chain)
- Observation -> "Per-instance series diverged sharply for a short window" (case-monitoring-alert-delay-histogram-skew.md:Event Logic Chain)
- Mechanism -> "vmagent scrape timing was not aligned across instances" (case-monitoring-alert-delay-histogram-skew.md:Event Logic Chain)
- Mechanism -> "Histogram bucket aggregation skew distorted the percentile" (case-monitoring-alert-delay-histogram-skew.md:Event Logic Chain)
- Pipeline model -> "Rule engine decides whether an alert is pending/firing" (case-monitoring-alert-delay-histogram-skew.md:Alerting Architecture)
- Delay model -> "Bad receiver -> Alertmanager queue backs up -> notification delivery delayed" (case-monitoring-alert-delay-histogram-skew.md:Why Alerts Are Delayed)
- Note -> "Evidence mapping aligns each key judgment to stable source headings for traceability." (case-monitoring-alert-delay-histogram-skew.md:Evidence Mapping)
