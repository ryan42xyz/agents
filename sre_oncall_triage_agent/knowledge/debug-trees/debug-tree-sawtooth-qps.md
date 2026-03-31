---
metadata:
  kind: debug-tree
  status: stable
  summary: "Diagnose periodic spike-and-drop (sawtooth) QPS pattern on Loki-derived recording rules"
  tags: ["qps", "sawtooth", "loki", "recording-rule", "429", "rate-limit"]
  first_action: "mcp__victoriametrics__rules: rule_names=['{metric_name}'], type='record'"
  routing_cluster: "Cluster 4 — False Signals"
  related:
    - patterns/pattern-ingress-rate-limit-429-window-mismatch.md
---

# Debug Tree: Sawtooth QPS on Loki-Derived Recording Rule

## Match Condition

- QPS chart shows periodic spike-and-drop pattern (sawtooth / comb shape)
- Source metric is a Loki-derived recording rule (name contains "loki", "recording", or "record:")
- Spike period is regular (same interval between peaks, e.g., every ~4 minutes)
- Spikes are large relative to baseline (e.g., baseline ~10 QPS, spikes ~100+ QPS)

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| client | yes | triage extraction |
| cluster | yes | triage extraction or metric labels |
| metric_name | yes | the recording rule metric name |
| proxy_upstream_name | recommended | dashboard legend or metric labels |
| request_url | recommended | dashboard legend or metric labels |

## Steps

### Step 1: Verify recording rule health

- **Tool**: `mcp__victoriametrics__rules`
- **Query**: `rule_names=["{metric_name}"]`, `type="record"`
- **Extract**: `health`, `lastError`, `lastSamples`, `evaluationTime`, `lastSeriesFetched`
- **Branch**:
  - `health=ok` AND `lastError=""` → CONTINUE Step 2
  - `health!=ok` OR `lastError!=""` → FINDING: "Recording rule unhealthy: {lastError}" → **ESCALATE** (rule evaluation problem)
  - Rule not found → FINDING: "Rule not found in vmalert" → **MANUAL** (check rule config)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("rule not returned by API — check rule name spelling")
  - other → ESCALATE

### Step 2: Enumerate raw metric label dimensions

- **Tool**: `mcp__victoriametrics__series`
- **Query**: `match="{raw_source_metric}{client='{client}'}"`, limit=10
  - Note: raw source metric is in the rule's `query` field from Step 1
- **Extract**: available label names, especially `status_code`, `pod`/`instance`, `method`
- **Branch**:
  - `status_code` exists as label → CONTINUE Step 3
  - `status_code` missing → FINDING: "Cannot disaggregate by status_code" → **MANUAL** (check other label dimensions)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("metric may not have status_code label — try other dimensions")
  - other → ESCALATE

### Step 3: Check 200 baseline stability

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `sum(rate({raw_source_metric}{client="{client}", status_code="200", proxy_upstream_name="{upstream}"}[1m]))`
- **Time**: `start=now-2h`, `end=now`, `step=1m`
- **Assess**: is the 200 rate smooth/stable or also bursty?
- **Branch**:
  - Smooth/stable (no drops to 0, coefficient of variation < 0.5) → CONTINUE Step 4
  - Also bursty/gappy → FINDING: "200 traffic also unstable — real traffic issue or promtail delivery gap" → **ESCALATE**
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("200 baseline query returned no data — metric may not exist for this client")
  - other → ESCALATE

### Step 4: Identify bursty status code

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `sum by (status_code) (rate({raw_source_metric}{client="{client}", proxy_upstream_name="{upstream}"}[1m]))`
- **Time**: `start=now-2h`, `end=now`, `step=1m`
- **Assess**: which status_code shows the periodic burst pattern?
- **Branch**:
  - `429` bursty, others flat → CONTINUE Step 5 (characterize burst)
  - `502` bursty → FINDING: "Upstream errors in bursts" → **ESCALATE** (upstream health issue)
  - Multiple codes bursty → FINDING: "Multiple status codes bursty — systemic issue" → **ESCALATE**
  - No bursty code found → FINDING: "Sawtooth not explained by status_code disaggregation" → **MANUAL** (try other label dimensions: pod, method)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result → MARK_UNKNOWN ("disaggregation query returned no data")
  - other → ESCALATE

### Step 5: Characterize 429 burst cadence

- **Tool**: `mcp__victoriametrics__query_range`
- **Query**: `sum(rate({raw_source_metric}{client="{client}", status_code="429", proxy_upstream_name="{upstream}"}[1m]))`
- **Time**: `start=now-6h`, `end=now`, `step=1m`
- **Assess**: measure interval between peaks
- **Branch**:
  - Regular interval (e.g., every 4min ± 30s) → **CONCLUSION**: `NON_ACTIONABLE_NOISE` — client-side batch scheduler hitting rate limit
  - Irregular bursts → FINDING: "Irregular 429 bursts — possibly promtail batch flush or log rotation catch-up" → **MANUAL** (check promtail logs)
- **on_error**:
  - timeout → RETRY_ONCE
  - empty result / cadence analysis fails → MARK_UNKNOWN ("cannot characterize burst cadence — report observed pattern from Step 4")
  - other → ESCALATE

## Resolution Template

```markdown
## Conclusion
- verdict: {NON_ACTIONABLE_NOISE | ESCALATE | MANUAL}
- confidence: {high | medium | low}
- evidence_chain: [Step 1: rule healthy → Step 3: 200 smooth → Step 4: 429 bursty → Step 5: regular {N}min cadence]
- root_cause: Bursty 429 responses from client batch retry, summed with smooth 200 traffic in recording rule
- recommended_action:
  - Confirm with client whether they have a scheduled batch job (period ~{N}min)
  - If unintended: advise exponential backoff / jitter
  - Optional: split 429 out of QPS dashboard or add status_code="200" filter
```

## Historical Cases

- **flutterwave detection EU (2026-03-29)**: 429 burst every 4min from client scheduler. 200 smooth. Verdict: NON_ACTIONABLE_NOISE.
