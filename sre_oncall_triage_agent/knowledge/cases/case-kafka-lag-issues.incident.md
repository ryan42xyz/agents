---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-kafka-lag-issues.md
  title: "Kafka Consumer Lag Spike (Downstream ClickHouse Parts Throttling/Backpressure)"
  summary: "Kafka consumer lag spiked across multiple topics at the same time; correlating with ClickHouse logs showed insert throttling due to too many parts; controlled consumer restarts can stop the bleeding quickly; long-term fixes are parts/merge and batching governance, and making ""check the sink first"" the default branch for lag triage."
  tags: [kafka, lag, consumers, clickhouse, kubernetes]
  patterns: [kafka-lag-from-sink-throttle]
---

# Incident: Kafka Consumer Lag Spike (Downstream ClickHouse parts throttling)

## 1. Incident Overview
- Date: 2025-06-14 (alert window recorded)
- Severity: TBD
- Duration: TBD
- System: Kafka -> consumer group (async consumer) -> ClickHouse
- Impact: multiple topics for a consumer group accumulated high lag (exact user impact: TBD)

## 2. System Context
- Architecture: producers -> Kafka topics -> consumer group -> ClickHouse inserts
- Coupling: consumer throughput is bounded by downstream sink latency/backpressure

## 3. Environment
- Environment: production (context suggests prod; exact cluster: sanitized)
- Platform: Kubernetes
- Streaming: Kafka
- Sink: ClickHouse

## 4. Trigger
- Trigger: Alertmanager reported high lag for the consumer group across multiple topics.

## 5. Impact Analysis
- Observed lag magnitude: thousands to tens of thousands (5-minute window)
- Blast radius: delayed downstream processing
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints
- Actions recorded: consumer pod restart used as mitigation (safe criteria and approvals: TBD)

## 7. Investigation Timeline
- 2025-06-14 ~00:21: alert fired for high lag.
- Correlated with ClickHouse logs; observed repeated "Delaying inserting block" messages due to large parts count.
- Hypothesis: downstream ClickHouse insert throttling reduced consumer throughput and caused lag.
- Mitigation: restart consumer pods (async consumer).
- Verification: lag caught up and returned to baseline.

## 8. Root Cause
- Root cause: ClickHouse insert throttling due to excessive parts count (parts explosion), slowing writes and reducing consumer throughput.
- Symptom vs root cause:
  - Symptom: Kafka lag spikes
  - Root cause: downstream ClickHouse write bottleneck

## 9. Mitigation
- Mitigation: restart async-consumer pods (controlled restart).
- Verification: consumption completed and lag returned to normal.

## 10. Prevention / Improvement
- ClickHouse:
  - review partitioning/merge strategy; reduce small-part generation
  - tune batching and ingestion to avoid parts explosion
  - alert on parts count and insert throttling lines
- Consumers:
  - make downstream write latency a first-class SLI; expose backpressure signals
  - right-size resources/autoscaling for spike loads
- Runbook:
  - Kafka lag triage should check sinks (ClickHouse) early

## 11. Generalizable Lessons
- Kafka lag is a symptom; shared bottlenecks (consumer capacity, sink latency) often dominate.
- If many topics lag simultaneously, suspect shared downstream dependencies.
- Controlled restarts can reduce incidental stuckness but do not remove the bottleneck.
- Pattern Card:
  - Pattern name: kafka-lag-from-sink-throttle
  - When it happens: sink inserts throttle (e.g., ClickHouse parts too many)
  - Fast detection signals: lag spike + sink logs show throttling
  - Fast mitigation: reduce sink pressure / restart consumers (temporary)
- Common pitfalls: blaming Kafka brokers; ignoring sink logs

## Tags & Patterns
- Tags: kafka, lag, consumers, clickhouse, kubernetes
- Patterns: kafka-lag-from-sink-throttle
- First Action: confirm the lag scope (consumer group plus topics plus time window), then check ClickHouse write health

## Evidence Mapping
- Time -> "Time window: around 2025-06-14 00:21" (case-kafka-lag-issues.md:Triage - Symptoms)
- Symptom -> "Alertmanager: consumer group cg.<prod-cluster> had high lag across multiple Kafka topics" (case-kafka-lag-issues.md:Triage - Symptoms)
- Sink clue -> "ClickHouse table had too many parts; inserts were forcibly delayed/throttled" (case-kafka-lag-issues.md:Triage - Interpretation)
- Correlation -> "Kafka lag increase coincided with ClickHouse insert delays" (case-kafka-lag-issues.md:Triage - Clues)
- Mitigation -> "Restarted async-consumer pods; lag symptom disappeared" (case-kafka-lag-issues.md:Triage - Actions Taken)
- Verification -> "Consumers caught up and lag returned to normal" (case-kafka-lag-issues.md:Triage - Follow-up Check)
- Root-cause hint -> "Delaying inserting block" (case-kafka-lag-issues.md:Notes - Alertmanager/ClickHouse logs snippet)
