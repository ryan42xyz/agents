---
metadata:
  kind: structured-triage-trace
  status: final
  source: case-kafka-lag-issues.incident.md
  schema_version: "0.1"
  tags: ["kafka", "lag", "clickhouse", "parts-explosion", "backpressure"]
  failure_domain: "stateful systems / write pressure"
  cluster: "Cluster 3 — Stateful systems under write, IO, or catchup pressure"
---

# Structured Triage Trace: Kafka Consumer Lag (Downstream ClickHouse Parts Explosion)

---

## Signal

```
alert:     consumer group cg.<prod-cluster> lag HIGH on multiple topics
signal:    multi-topic lag spike, same consumer group, same time window
→ cluster: Cluster 3 (Stateful pressure / false surface signals)
→ reason:  multi-topic lag in one CG at same time → systemic bottleneck,
           not per-partition failure; downstream write sink is the prime suspect
```

### Routing Logic

```
IF   alert_type == kafka_consumer_lag_high
AND  scope == multi_topic_same_consumer_group
THEN suspect = downstream_write_bottleneck (not Kafka itself)
     first_action = check downstream sink before checking consumer health

IF   alert_type == kafka_consumer_lag_high
AND  scope == single_topic_or_single_partition
THEN suspect = consumer/partition/broker issue (different path)
```

---

## Decision Trace

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Confirm lag scope | Grafana Kafka lag dashboard | Multiple topics in same CG spiking at same time | Systemic issue, not per-partition; points to sink or consumer process | 0.80 |
| 2 | Check ClickHouse insert latency | Grafana CH dashboard / logs | `Delaying inserting block by Xms because there are N parts` in CH logs | CH actively backpressuring writes; parts count exceeded threshold | 0.90 |
| 3 | Check CH parts count trend | Prometheus / CH metrics | Parts count elevated (e.g. 1015 → 1058 in seconds) | Parts explosion in progress; merge cannot keep up with insert rate | 0.92 |
| 4 | Check consumer pod health | `kubectl get pods` + logs | Consumer pods running, no OOM/CrashLoop | Consumer is alive but blocked on CH write ack | 0.85 |
| 5 | Correlate timelines | Dashboard overlay | CH backpressure onset time matches lag spike onset | Causal direction: CH bottleneck → write slowdown → lag accumulation | 0.95 |
| 6 | Restart consumer pods | `kubectl rollout restart` (#MANUAL) | Lag begins catching up within minutes | Consumer re-established connection; unblocked from stuck write state | 0.90 |
| 7 | Monitor lag recovery | Kafka lag dashboard | Lag returns to baseline within 15-30 min, stays stable | Issue resolved; no structural fix yet applied | 0.95 |

---

## Evidence Chain

```
root_cause: clickhouse_parts_explosion_caused_insert_backpressure
  mechanism: CH inserts are delayed when active parts count exceeds threshold
             (system.merge_tree_settings: parts_to_delay_insert)
             → each insert blocks → consumer throughput drops → lag accumulates
  evidence:
    - step 2: CH log signature "Delaying inserting block ... N parts"
    - step 3: parts count rising monotonically
    - step 5: timeline correlation — CH backpressure onset == lag spike onset

contributing_factor: consumer process stuck in degraded write state
  evidence: step 6 — restart unblocked it without any CH fix applied

ruled_out:
  - Kafka broker issue (multi-topic same CG pattern; broker problems show differently)
  - Consumer OOM / CrashLoop (step 4: pods healthy)
  - Network partition (CH accessible, writes just slow)
  - Single-tenant QPS spike (multi-topic pattern)

mitigation_applied: consumer restart (short-term; does not fix CH parts explosion)

structural_fix_needed:
  - reduce CH parts explosion risk (batch sizing, merge policy, partition strategy)
  - add alerting on parts count and insert delay before lag alert fires
```

---

## Triage Policy (Extracted)

```yaml
policy_name: kafka-lag-downstream-write-bottleneck

trigger:
  alert: kafka_consumer_lag_high
  condition: multi_topic, same consumer group, same time window

steps:
  - id: step_1
    action: confirm_lag_scope
    tool: grafana_kafka_dashboard
    signal: which topics, which CG, continuous increase vs brief spike
    gate: IF single topic only → pivot to per-partition / broker triage
    on_multi_topic: continue

  - id: step_2
    action: check_downstream_sink_health
    tool: clickhouse_logs + grafana_ch_dashboard
    signal: "Delaying inserting block" log + insert latency metric
    gate: IF CH healthy (no delay logs, normal latency) → pivot to consumer health check
    on_backpressure_found: root_cause_direction = downstream_ch_bottleneck

  - id: step_3
    action: check_ch_parts_count
    tool: prometheus
    query: "SELECT active_parts FROM system.parts WHERE ..."
    gate: IF parts normal → check merge CPU, disk IO
    on_elevated: root_cause = parts_explosion_confirmed

  - id: step_4
    action: check_consumer_pod_health
    tool: kubectl
    command: "kubectl get pods -n <ns> && kubectl logs <consumer-pod>"
    gate: IF OOM or CrashLoop → consumer capacity issue (different fix path)
    on_healthy: consumer stuck (not crashed); restart may unblock

  - id: step_5
    action: correlate_timelines
    tool: grafana
    signal: overlay CH backpressure onset vs lag spike onset
    gate: IF timelines do not align → look for other causes
    on_aligned: causal direction confirmed

  - id: step_6
    action: restart_consumer_pods
    tool: kubectl
    command: "kubectl rollout restart deploy/<async-consumer> -n <ns>"
    type: "#MANUAL"
    gate: always requires human approval
    post: monitor lag recovery for 15-30 min

verification:
  - lag_baseline: lag returns to normal AND stays stable >= 15-30 min
  - ch_signals: insert delay logs stop, parts count returning to normal range
  - no_repeat: no re-alert on same CG in next 30+ min

human_gates:
  - consumer restart/rollout
  - any ClickHouse schema or settings change
  - consumer scaling
```

---

## Verifier Checklist

Before closing:

- [ ] Lag has returned to baseline on all affected topics
- [ ] Lag has been stable for >= 15 minutes (not just a brief dip)
- [ ] CH `Delaying inserting block` log entries have stopped
- [ ] CH parts count is trending down or stable in normal range
- [ ] Every `#MANUAL` action logged with who/when/what
- [ ] Follow-up items filed (parts alerting, merge policy review)

---

## Blast Radius

```
action_surface:  read-only for all diagnostic steps
human_gates:     consumer restart (step 6) — requires explicit approval
                 CH settings change (structural fix) — higher risk, separate review
rollback_path:   consumer restart is low-risk; rollback = restart again
escalation:      if CH parts not recovering after consumer restart → escalate to CH owner
                 if lag continues to climb post-restart → escalate to platform team
```

---

## Closeout Artifact

```
Status: MITIGATED (short-term)

Root cause: ClickHouse parts explosion caused insert backpressure,
            reducing consumer write throughput, amplifying Kafka lag.

Mitigation applied:
  - Restarted async-consumer pods (#MANUAL)
  - Lag recovered to baseline within ~15 min

Structural gaps (not fixed):
  - No alert on CH parts count or insert delay
  - No merge/batch tuning applied
  - Consumer has no backpressure SLI

Follow-up items:
  - [ ] Add Prometheus alert: CH active_parts > threshold
  - [ ] Add alert: CH insert_delay_ms P99 > Xms sustained > 2min
  - [ ] Review CH merge policy and batch insert sizing
  - [ ] Add consumer throughput / backpressure SLI to dashboard
```

---

## Pattern Cross-Reference

```
pattern_name:   kafka-lag-downstream-write-bottleneck
related_cases:  case-clickhouse-copydata-recovery-failure (CH stateful pressure variant)
                case-kafka-kraft-livenessprobe-restart-loop (consumer health variant)

key_principle:
  "Kafka lag is usually a symptom, not the root cause.
   Multi-topic lag in one CG → look downstream first (sink), not at Kafka.
   Stateful systems fail with 'still alive but not serving' — not clean up/down."

cluster_rule:
  "In Cluster 3, the first question is always:
   is the system under write/IO/catchup pressure, or is it the consumer that's broken?
   CH backpressure and consumer restart are different fixes — don't conflate them."
```
