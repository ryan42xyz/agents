---
metadata:
  kind: case
  status: final
  summary: "An oncall note for a delayed/false monitoring alert: scrape time misalignment plus histogram bucket aggregation skew inflated P99; Prometheus looked slow, but application logs/APM showed no slow requests."
  tags: ["monitoring", "prometheus", "histogram", "p99"]
  first_action: "Before trusting P99, use logs/APM to prove real latency"
  related:
    - ./case-monitoring-alert-delay-histogram-skew.incident.md
    - ./reference-grafana-vmalert-aws-k8s-links.md

---

# Delayed/False Monitoring Alert: Histogram Skew Inflated P99

## TL;DR (Do This First)
1. Disprove/confirm real user latency first: check application logs/APM in the same time window.
2. Check error rate: if it is not elevated, suspect false alert/observability skew first.
3. Compare per-instance histogram buckets and scrape alignment: short-lived divergence strongly indicates metrics skew.

## Safety Boundaries
- Read-only: view dashboards/PromQL, check application logs/APM, `kubectl get/describe/logs`, inspect Rule/Alert status.
- `#MANUAL`: silence/unsilence, change alert rules/recording rules, adjust scrape interval, restart/rollout vmagent/promtail/vmalert/Prometheus.



## Related
- [case-monitoring-alert-delay-histogram-skew.incident.md](./case-monitoring-alert-delay-histogram-skew.incident.md)
- [reference-grafana-vmalert-aws-k8s-links.md](./reference-grafana-vmalert-aws-k8s-links.md)

## Triage
- Align the time window first; do not reason across inconsistent time ranges.
- Confirm whether latency is real (logs/APM), and whether error rate supports it.
- If only P99 is high: compare per-instance histograms and scrape timestamps to find skew.
- Confirm the alert lifecycle state (`pending`/`firing`/`resolved`) is decided by the rule engine; Slack may show historical firing.

Alert state sanity check (keep it minimal):
- Whether it is `inactive`/`pending`/`firing` is decided by the rule engine; Alertmanager only delivers notifications.
- Rule engine APIs: `api/v1/rules` (rule definitions + status) and `api/v1/alerts` (currently firing alerts).

## Verification
- Logs/APM show no slow requests in the same time window (rule out real latency).
- Evidence of metrics skew exists (instance divergence + scrape misalignment + histogram aggregation sensitivity).
- After mitigation (rule tweak/`for:`/recording rule/scrape alignment), the alert no longer re-triggers in the same pattern.

## Closeout
- Communicate clearly: false alert, no user impact, and link to evidence (logs/APM + skew explanation).
- Record guardrails (must validate with logs/APM; add `for:`; prefer recording rules for percentiles).
- If it repeats, file follow-ups for the owner (scrape alignment, rule hardening).

Closeout message template:

```text
Confirmed false alert.

No real latency observed in application logs/APM in the same time window.
Metric skew (scrape misalignment + histogram aggregation sensitivity) inflated P99.

No production impact.
```

## One-line Essence
> Scrape time misalignment plus histogram aggregation skew inflated P99, causing a false latency alert.
