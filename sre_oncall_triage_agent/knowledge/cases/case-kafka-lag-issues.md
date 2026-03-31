---
metadata:
  kind: case
  status: final
  summary: "A troubleshooting framework for Kafka consumer lag incidents: start from multi-topic lag spikes (e.g., cg.<prod-cluster>) and correlate with downstream ClickHouse parts explosion causing insert backpressure; capture short-term mitigation (restart async consumer), a dashboard/log driven decision flow, and longer-term prevention."
  tags: ["kafka", "lag", "clickhouse", "consumers"]
  first_action: "Check lag first, then downstream ClickHouse insert latency/parts"
  related:
    - ./case-kafka-lag-issues.incident.md
    - ./card-db-issue-fast-entrypoints.md
    - ./card-fp-infra-fast-entrypoints.md
    - ./card-clickhouse-merge-pressure-fast-signals.md
    - ./runbook-database-incident-troubleshooting.md
---

# Kafka Consumer Lag Spike: Downstream ClickHouse Parts Explosion Bottleneck

## TL;DR (Do This First)
1. Confirm scope: consumer group + topics + cluster + time window
2. Common first check (start downstream): ClickHouse insert latency and the `Delaying inserting block ... parts` signature
3. Check consumer (async consumer) health: restarts/CPU/memory/errors/throughput
4. Fast mitigation: restart consumer pods to unstick (`#MANUAL`)
5. Verify lag drops and ClickHouse write-pressure signals decrease

## Safety Boundaries
- Read-only: dashboards, lag metrics, ClickHouse metrics/logs, `kubectl get/describe/logs`
- `#MANUAL`: restart/rollout/scale consumers (e.g., async consumer), change ClickHouse settings/schema



## Related
- [case-kafka-lag-issues.incident.md](./case-kafka-lag-issues.incident.md)
- [card-db-issue-fast-entrypoints.md](./card-db-issue-fast-entrypoints.md)
- [card-fp-infra-fast-entrypoints.md](./card-fp-infra-fast-entrypoints.md)
- [card-clickhouse-merge-pressure-fast-signals.md](./card-clickhouse-merge-pressure-fast-signals.md)
- [runbook-database-incident-troubleshooting.md](./runbook-database-incident-troubleshooting.md)

## One-line Essence
- Kafka lag is usually a symptom; here, downstream ClickHouse parts explosion caused insert backpressure, reduced write throughput, and increased lag.

## Triage
- Confirm lag scope (group/topics/cluster/time window), then prioritize downstream: ClickHouse insert latency + `Delaying inserting block ... parts` logs.
- If ClickHouse looks healthy but the consumer is unhealthy (OOM/restarts/throttling), treat as a consumer capacity/stuck issue; consider controlled restarts (`#MANUAL`).
- If ClickHouse is clearly backpressured, reduce sink pressure (parts/merge/batching) before scaling consumers.

## Verification
- Lag returns to baseline and stays stable for >= 15-30 minutes.
- ClickHouse write-pressure signals decrease (insert delay/backpressure logs stop worsening; parts/merge pressure returns to normal range).
- No repeat alerts for the same group/topics in the next 30+ minutes.

## Closeout
- Close when verification conditions are met, and ensure every `#MANUAL` action (restart/scale) has timestamp + rationale recorded.
- Record follow-ups: ClickHouse parts governance + dashboards/alerts; consumer backpressure/throughput SLI.

## Trigger / Symptoms
- Alertmanager: consumer group `cg.<prod-cluster>` lag high on multiple topics (e.g., `topic.<tenant-a>`/`topic.<tenant-b>`/`topic.<workload>`)
- Time: <date> <time-window>
- ClickHouse shows repeated insert backpressure logs: `Delaying inserting block ... because there are <N> parts`

## Investigation Notes

### 1) Confirm lag scope
- Record: consumer group, topics, cluster, and whether it is multi-topic or single-topic
- Use dashboards to confirm lag is continuously increasing (not a brief spike)

### 2) Correlate with downstream ClickHouse
- Look for: rising insert latency, merge pressure, parts explosion, disk pressure
- The ClickHouse log signature alone is often enough to classify it as downstream write backpressure

### 3) Check consumer (async consumer) health
- Look for: restarts/CrashLoop, OOM/throttling, error spikes, commit/processing rate drop

### 4) Actions taken (record)
- Restarted async-consumer pods; lag recovered back to baseline

## Root Cause (Best-Effort)
- Most likely: ClickHouse parts explosion caused insert delay/backpressure, reducing consumer write throughput and amplifying Kafka lag.
- Secondary factors to validate if it recurs: consumer resources/backpressure tuning, load imbalance (cluster-a QPS spike affecting cluster-b topics).

## Verification / Isolation Experiments (Recommended)

Goal: prove whether lag is driven by downstream ClickHouse writes or by the consumer/Kafka itself.

### Step A: Time correlation
- If the lag spike aligns with a ClickHouse `Delaying inserting block` spike, treat it as a downstream bottleneck first.

### Step B: Differential diagnosis
- ClickHouse normal but consumer unhealthy (OOM/restarts/throttling): consumer/capacity issue.
- ClickHouse abnormal but consumer healthy: downstream bottleneck (parts/merge/write pressure).

### Step C: Close criteria
- Lag returns to baseline and stays stable for >= 15-30 minutes
- ClickHouse insert delay/parts/backpressure signals return to normal range
- No repeat alerts for the same group/topics in the next 30+ minutes

Decision flow:

```mermaid
flowchart TD
    A[Kafka lag alert] --> B[Confirm scope in dashboard]
    B --> C[Check consumer pods: async consumer]
    C --> D{Consumer unhealthy?}
    D -->|Yes| E[Restart/scale async consumer (#MANUAL)]
    D -->|No| F[Check ClickHouse logs/metrics]
    F --> G{Delaying insert / parts too many?}
    G -->|Yes| H[Downstream CH bottleneck; fix parts/merge/backpressure]
    G -->|No| I[Continue: Kafka broker/network/other deps]
    E --> J[Verify lag catch-up]
    H --> J
    I --> J
    J --> K[Record evidence + follow-ups]
```

## Resolution
- `#MANUAL`: restarted async-consumer pods
- Verified lag caught up and alert cleared

## Prevention / Follow-ups
- ClickHouse: reduce parts explosion risk (merge/partition strategy, batch sizing), add alerts on parts count + insert delay
- Consumer: add throughput/backpressure observability; ensure resources/autoscaling cover peak QPS
- Oncall: codify a standard branch: lag + `Delaying inserting block` => treat as downstream write bottleneck first

## Evidence Snippets

Dashboards:
- `<internal-dashboard-index>`
- Grafana (Kafka exporter): `<internal-grafana-link>`

Alert excerpt:
```text
Alertmanager
APP  Saturday at 3:08 PM
[HIGH][RT] cluster: <prod-cluster>, namespace: kubernetes-pods <internal-ip>:<port>: The consumer group cg.<prod-cluster> Topic: topic.<tenant-a> lag is High. Current value is <value> of last 5 minutes.
[HIGH][RT] cluster: <prod-cluster>, namespace: kubernetes-pods <internal-ip>:<port>: The consumer group cg.<prod-cluster> Topic: topic.<tenant-b> lag is High. Current value is <value> of last 5 minutes.
Click <internal-alert-console-link> to check all alerts status.
```

ClickHouse log signature:
```text
2025.06.14 07:21:10.682101 [ 19422 ] ... <Information> ...: Delaying inserting block by 10 ms. because there are 1015 parts ...
2025.06.14 07:21:16.328843 [ 19425 ] ... <Information> ...: Delaying inserting block by 11 ms. because there are 1058 parts ...
looks like clickhouse issue
```

Operator note (recorded):
```text
It has been consume completed. back normal
seem that i restarted async-consumer pod and the issue was gone
```
