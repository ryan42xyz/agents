---
metadata:
  kind: debug-tree
  status: stable
  summary: "Kafka consumer lag: multi-topic → downstream write bottleneck (ClickHouse parts/insert pressure)"
  tags: ["kafka", "lag", "clickhouse", "consumers", "write-pressure"]
  first_action: "Check lag scope: multi-topic same consumer group → systemic downstream issue"
  routing_cluster: "Cluster 3 — Stateful/Write Pressure"
  related:
    - cases/case-kafka-lag-issues.md
    - references/reference-db-issue-quick-reference.md
    - cards/card-db-issue-fast-entrypoints.md
---

# Debug Tree: Kafka Consumer Lag — Downstream ClickHouse Write Bottleneck

## Match Condition

- Kafka consumer lag alert fires on **multiple topics** within the **same consumer group** at the same time
- Lag is continuously increasing (not a brief spike that self-resolves)
- Consumer group pattern: `cg.<prod-cluster>`
- No consumer pod crashes or OOM events visible at alert time

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| consumer_group | yes | alert payload / Kafka dashboard |
| affected_topics | yes | alert payload / Kafka dashboard |
| cluster | yes | alert payload |
| namespace | yes | alert payload or `kubectl` |
| clickhouse_instance | yes | architecture knowledge or dashboard |
| time_window | yes | alert timestamp |

## Steps

### Step 1: Confirm lag scope — multi-topic or single-topic

- **Tool**: `mcp__grafana__query_prometheus`
- **Query**: `sum by (topic) (kafka_consumergroup_lag{consumergroup="{consumer_group}", cluster="{cluster}"})`
- **Extract**: which topics are lagging, whether lag is rising monotonically
- **Branch**:
  - Multiple topics in same CG spiking at same time → **systemic downstream issue** → CONTINUE Step 2
  - Single topic or single partition only → **per-partition / broker issue** → different triage path (check partition leader, broker health, consumer assignment)
  - Brief spike already recovering → **transient** → monitor only, do not escalate
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (lag metric may not be exposed; check Kafka dashboard manually)
  - other → ESCALATE

### Step 2: Check ClickHouse insert latency and backpressure logs

- **Tool**: `mcp__grafana__query_prometheus`
- **Query**: `histogram_quantile(0.99, sum by (le) (rate(clickhouse_insert_query_duration_seconds_bucket{instance="{clickhouse_instance}"}[5m])))`
- **Also check**: ClickHouse pod logs for the signature `Delaying inserting block by Xms because there are N parts`
- **Tool (logs)**: `kubectl logs -n {namespace} {clickhouse_pod} --since=30m | grep -i "Delaying inserting block"`
- **Branch**:
  - `Delaying inserting block` log present AND insert latency elevated → **CH backpressure confirmed** → CONTINUE Step 3
  - CH logs clean, insert latency normal → **downstream healthy** → pivot to Step 4 (consumer health) as primary suspect
  - CH unreachable or connection errors → **CH availability issue** → ESCALATE to CH owner
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (insert latency metric may not be available; continue to Step 3)
  - other → ESCALATE

### Step 3: Check ClickHouse parts count trend

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `clickhouse_table_parts{instance="{clickhouse_instance}", database="{database}"}`
- **Time**: `start=now-2h`, `end=now`, `step=1m`
- **Assess**: is parts count rising monotonically? Has it crossed `parts_to_delay_insert` threshold?
- **Branch**:
  - Parts count elevated and rising (e.g., 1000+) → **parts explosion in progress**; merge cannot keep up → CONTINUE Step 4
  - Parts count normal / stable → backpressure may be transient; check merge CPU and disk IO → CONTINUE Step 4
  - Parts count extremely high (e.g., 3000+) → **critical CH state** → ESCALATE to CH owner immediately
- **on_error**:
  - timeout → RETRY_ONCE
  - metric not found → FALLBACK_QUERY (`clickhouse_table_parts` or `system_parts_count`)
  - empty result → MARK_UNKNOWN (parts metric unavailable; continue to Step 4)
  - other → ESCALATE

### Step 4: Check consumer pod health

- **Tool**: `kubectl`
- **Command**: `kubectl get pods -n {namespace} -l app={consumer_app} -o wide` and `kubectl logs -n {namespace} {consumer_pod} --tail=100`
- **Extract**: pod status, restart count, OOM events, error logs, last commit/processing timestamps
- **Branch**:
  - Pods Running, no restarts, no OOM → **consumer alive but blocked on CH write ack** → CONTINUE Step 5
  - OOM / CrashLoopBackOff → **consumer capacity issue** → restart or scale consumer (`#MANUAL`), then re-check lag
  - Error logs showing connection refused / timeout to CH → confirms CH bottleneck from Step 2
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

### Step 5: Correlate timelines — CH backpressure onset vs lag spike onset

- **Tool**: `mcp__grafana__query_prometheus`
- **Query (lag)**: `sum(kafka_consumergroup_lag{consumergroup="{consumer_group}", cluster="{cluster}"})`
- **Query (CH insert delay)**: `rate(clickhouse_insert_delayed_total{instance="{clickhouse_instance}"}[5m])`
- **Time**: overlay both on same time range (last 2-4 hours)
- **Assess**: does CH backpressure onset time match lag spike onset?
- **Branch**:
  - Timelines align (CH backpressure starts at or before lag spike) → **causal direction confirmed**: CH bottleneck → write slowdown → lag accumulation → CONTINUE Step 6
  - Timelines do not align (lag starts before CH pressure) → look for other causes: consumer code regression, network partition, QPS spike → **MANUAL** investigation
  - Insufficient data → **MANUAL** (check dashboard overlays in Grafana directly)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN (correlation metric unavailable; proceed to Step 6 based on prior evidence)
  - other → ESCALATE

### Step 6: Restart consumer pods (`#MANUAL`)

- **Tool**: `kubectl`
- **Command**: `# INTENT: consumer stuck in degraded write state due to CH backpressure; restart to re-establish connection`
  `kubectl rollout restart deploy/{consumer_deployment} -n {namespace}`
- **Type**: `#MANUAL` — requires explicit human approval before execution
- **Post-action verification**:
  - `kubectl rollout status deploy/{consumer_deployment} -n {namespace}`
  - Monitor lag for 15-30 minutes: `sum(kafka_consumergroup_lag{consumergroup="{consumer_group}"})`
- **Branch**:
  - Lag begins catching up within minutes and returns to baseline within 15-30 min → **RESOLVED** (short-term mitigation)
  - Lag does not recover after restart → CH still backpressuring; ESCALATE to CH owner for merge/parts intervention
  - Lag recovers then re-spikes → structural issue; file follow-up for CH parts governance
- **on_error**:
  - command fails → ESCALATE (cluster access issue; manual gate step requires working kubectl)
  - other → ESCALATE

## Resolution Template

```markdown
## Conclusion
- verdict: {MITIGATED | ESCALATE | MANUAL}
- confidence: {high | medium | low}
- evidence_chain: [Step 1: multi-topic lag confirmed → Step 2: CH "Delaying inserting block" log found → Step 3: parts count {N} and rising → Step 5: timeline correlation confirmed → Step 6: consumer restart, lag recovered in {M} min]
- root_cause: ClickHouse parts explosion caused insert backpressure, reducing consumer write throughput, amplifying Kafka lag across all topics in consumer group {consumer_group}
- mitigation_applied: Restarted {consumer_deployment} pods (#MANUAL)
- structural_fix_needed:
  - Add Prometheus alert on CH active_parts > threshold
  - Add alert on CH insert_delay_ms P99 > Xms sustained > 2min
  - Review CH merge policy and batch insert sizing
  - Add consumer throughput / backpressure SLI to dashboard
- verification:
  - Lag returned to baseline and stable >= 15 min
  - CH "Delaying inserting block" logs stopped
  - No re-alert on same CG in next 30+ min
```

## Historical Cases

- **Kafka lag multi-topic spike (case-kafka-lag-issues)**: Consumer group `cg.<prod-cluster>` lag high on multiple topics simultaneously. CH logs showed `Delaying inserting block by 10ms because there are 1015 parts` rising to 1058. Consumer pods were healthy but blocked. Restarted async-consumer pods; lag recovered to baseline within ~15 min. Root cause: CH parts explosion causing insert backpressure. Verdict: MITIGATED (short-term). Structural follow-ups filed for parts alerting and merge policy review.
