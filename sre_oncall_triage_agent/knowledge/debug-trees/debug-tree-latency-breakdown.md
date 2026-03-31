---
metadata:
  kind: debug-tree
  status: stable
  summary: "Break down latency into FP service vs network/ingress components using request_time - upstream_response_time"
  tags: ["latency", "fp", "ingress", "sla", "p95", "upstream-response-time"]
  first_action: "mcp__victoriametrics__query_range: histogram_quantile(0.95, sum by (le) (rate(record:loki_kubernetes_monitoring_request_time_ingress_nginx_bucket{client='{client}'}[5m])))"
  routing_cluster: "Cluster 1 — Routing/Ingress or service-specific"
  related:
    - cases/case-fp-latency-waiting-latency-prod-qps-spike.md
    - patterns/pattern-fp-latency-waiting-latency-pattern.md
    - checklists/checklist-fp-latency-uswest-preprod-checklist.md
    - cards/card-fp-infra-fast-entrypoints.md
---

# Debug Tree: Latency Breakdown (FP vs Network/Ingress)

## Match Condition

- Alert mentions latency, response time, or SLA degradation
- Client reports slow responses or timeouts
- SLA dashboard shows elevated request_time percentiles

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| client | yes | triage extraction |
| cluster | recommended | triage extraction |
| pipeline | recommended | alert labels (batch/realtime) |
| time_window | yes | alert time or default now-2h→now |

## Steps

### Step 1: Query SLA dashboard metrics — Total Response Time

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `histogram_quantile(0.95, sum by (le) (rate(record:loki_kubernetes_monitoring_request_time_ingress_nginx_bucket{client="{client}"}[5m])))`
  - Or use Grafana MCP: `mcp__grafana__query_prometheus` against the SLA dashboard's recording rule
- **Time**: `start={time_window_start}`, `end={time_window_end}`, `step=1m`
- **Assess**: is P95 total response time above threshold?
- **Branch**:
  - P95 < 300ms → FINDING: "Total response time within normal range" → **CONCLUSION**: `NON_ACTIONABLE_NOISE`
  - P95 300-500ms → FINDING: "Yellow warning range" → CONTINUE Step 2
  - P95 > 500ms → FINDING: "Red alert range" → CONTINUE Step 2
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result / metric not found → ESCALATE ("cannot determine total response time — critical for scenario routing")
  - other → ESCALATE

### Step 2: Query Upstream Response Time

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `histogram_quantile(0.95, sum by (le) (rate(record:loki_kubernetes_monitoring_upstream_response_time_ingress_nginx_bucket{client="{client}"}[5m])))`
- **Time**: same as Step 1
- **Assess**: is upstream response time high?
- **Branch**:
  - Upstream P95 > 300ms → **Scenario A**: FP service issue → CONTINUE Step 3A
  - Upstream P95 < 150ms → **Scenario B**: Network/Ingress issue → CONTINUE Step 3B
  - Upstream P95 150-300ms → assess waiting_latency → CONTINUE Step 2B
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result / metric not found → ESCALATE ("cannot determine upstream response time — critical for scenario routing")
  - other → ESCALATE

### Step 2B: Calculate Waiting Latency

- **Derive**: `waiting_latency = request_time - upstream_response_time`
- **Assess**: is waiting latency the dominant component?
- **Branch**:
  - Waiting latency > upstream response time → **Scenario B**: Network/Ingress issue → CONTINUE Step 3B
  - Upstream response time > waiting latency → **Scenario A**: FP service issue → CONTINUE Step 3A
  - Both elevated → **Scenario C**: Systemic issue → CONTINUE Step 3C
- **on_error**:
  - insufficient data for calculation (Step 1 or Step 2 returned incomplete series) → MARK_UNKNOWN ("cannot derive waiting_latency — default to Scenario A")
  - other → ESCALATE

### Step 3A: FP Service Issue — Check Dependencies

- **Tool**: `mcp__victoriametrics__query_range`
- **Query sequence** (priority order):
  1. **P0 — YugabyteDB**: `ybdb_query_latency{client="{client}"}` or relevant DB metric
  2. **P1 — External API (Ekata)**: response time metrics for external calls
  3. **P2 — MySQL**: `mysql_query_duration{client="{client}"}`
  4. FP Pod CPU/Memory: `container_cpu_usage_seconds_total{pod=~"fp.*", namespace=~".*{client}.*"}`
- **Branch**:
  - DB latency high → **CONCLUSION**: `NEEDS_ATTENTION` — database performance degradation
  - External API slow → **CONCLUSION**: `NEEDS_ATTENTION` — external dependency issue
  - Pod resources saturated → **CONCLUSION**: `NEEDS_ATTENTION` — capacity issue
  - All normal → FINDING: "FP slow but no obvious dependency bottleneck" → **MANUAL** (check application logs)
- **on_error**:
  - timeout on any dependency query → RETRY_ONCE (per query)
  - empty result / metric not found on individual dependency → MARK_UNKNOWN ("dependency metric unavailable — continue checking others")
  - other → ESCALATE

### Step 3B: Network/Ingress Issue — Check Ingress Health

- **Tool**: `mcp__victoriametrics__query_range` / `mcp__grafana__query_loki_logs`
- **Query sequence**:
  1. Ingress controller CPU/Memory
  2. Connection timeout count in ingress logs
  3. Check if traffic switch recently occurred
- **Branch**:
  - Ingress controller resource saturated → **CONCLUSION**: `NEEDS_ATTENTION` — ingress capacity
  - Connection timeouts found → **CONCLUSION**: `NEEDS_ATTENTION` — network quality issue
  - Recent traffic switch → FINDING: "Traffic switch correlates with latency onset" → **ESCALATE**
  - All normal → FINDING: "Waiting latency high but ingress appears healthy" → **MANUAL** (check K8s network)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result on VM query → MARK_UNKNOWN ("ingress metric unavailable — continue with log check")
  - Loki query failure → FALLBACK_QUERY (try VM-based ingress error counters instead)
  - other → ESCALATE

### Step 3C: Systemic Issue

- **Tool**: multiple
- **Query sequence**:
  1. Check if all FP replicas are affected (not just one pod)
  2. Check for recent deployments: `kube_deployment_status_observed_generation`
  3. Check node health: `kube_node_status_condition`
- **Branch**:
  - Single pod affected → **CONCLUSION**: `NEEDS_ATTENTION` — pod-level issue, possible restart
  - Recent deployment correlates → **CONCLUSION**: `ESCALATE` — deployment-related regression
  - Multiple nodes unhealthy → **CONCLUSION**: `ESCALATE` — infrastructure issue
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result on any sub-query → MARK_UNKNOWN ("systemic check incomplete — report partial findings")
  - other → ESCALATE

## Reference Values

| Metric | Normal (P95) | Warning (P95) | Alert (P95) |
|--------|-------------|---------------|-------------|
| Total Response Time | < 300ms | 300-500ms | > 500ms |
| Upstream Response | < 150ms | 150-300ms | > 300ms |
| Waiting Latency | < 100ms | 100-200ms | > 200ms |

## Resolution Template

```markdown
## Conclusion
- verdict: {NON_ACTIONABLE_NOISE | NEEDS_ATTENTION | ESCALATE | MANUAL}
- confidence: {high | medium | low}
- scenario: {A: FP service | B: Network/Ingress | C: Systemic}
- evidence_chain: [Step 1 P95={val}ms → Step 2 upstream={val}ms → Step 3x: {finding}]
- root_cause: {description}
- recommended_action: {specific to scenario}
```

## Key Insight

Always start with SLA dashboard. The formula `request_time = waiting_latency + upstream_response_time` is the single most diagnostic check. It immediately tells you which layer to investigate.
