# Traffic Interface

## Purpose

Inspect traffic, ingress, and interface-level metrics.

## Scope

- Ingress traffic patterns
- API gateway metrics
- Interface-level errors
- Request rates and latencies
- Upstream/downstream relationships

## Inspection Checklist

1. Multi-cluster traffic distribution dashboard
   - Check traffic split across clusters
   - Verify interface-level routing
   - Identify traffic anomalies

2. Ingress logs and metrics
   - API gateway (APISIX) logs
   - Ingress controller metrics
   - Request/response patterns

3. Interface health
   - Status codes distribution
   - Request time percentiles
   - Upstream response times

## Principles

- Traffic metrics are symptoms, not root causes
- Check multiple interfaces if client uses multiple
- Consider time windows around alert time
- Do NOT assume all traffic is affected

## Anomaly Pattern: Sawtooth / Periodic Spike-and-Drop QPS

**When you see**: QPS chart shows regular oscillation (high → near-zero → high), especially on a Loki-derived recording rule.

**First move — disaggregate by `status_code` before anything else**:

```promql
# Step 1: is the 200 baseline smooth?
sum(rate(kubernetes_monitoring_request_total_ingress_nginx{
  client="$client", proxy_upstream_name="$upstream", request_url="$url",
  status_code="200"
}[1m] offset 1m))

# Step 2: which status code is bursty?
sum by (status_code) (rate(kubernetes_monitoring_request_total_ingress_nginx{
  client="$client", proxy_upstream_name="$upstream", request_url="$url"
}[1m] offset 1m))
```

**Decision tree**:
- 200 is smooth + 429 is bursty → `NON_ACTIONABLE_NOISE`; client-side batch retry hitting rate limit
- 200 is smooth + 502 is bursty → upstream errors; escalate
- 200 is also bursty/gappy → real traffic issue or promtail delivery gap; investigate further

**Loki-derived counter debug order**:
1. `mcp__victoriametrics__rules` — check rule health (health, lastError, lastSamples)
2. `mcp__victoriametrics__series` — enumerate label dimensions on raw metric
3. Raw counter per `pod`/`instance` — monotone = healthy; gaps = promtail issue; resets = counter reset
4. `rate()` per `status_code` — isolate which code carries the anomalous signal
5. Check burst cadence: regular interval (e.g., every 4min) → client scheduler; irregular → promtail batch or log rotation
