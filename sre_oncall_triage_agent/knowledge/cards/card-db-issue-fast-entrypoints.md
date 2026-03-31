---
metadata:
  kind: reference
  status: draft
  summary: "Card: Database issue quick entrypoints (Yugabyte/ClickHouse/MySQL/Kafka) - minimal health checks and first-line decision branches."
  tags: ["card", "database", "yugabyte", "clickhouse", "mysql", "kafka", "oncall"]
  first_action: "Confirm the affected DB first, then run minimal health checks"
---

# Card: Database Issues - Quick Entrypoints

## TL;DR (Do This First)
1. First confirm *which* backend is failing (YB/CH/MySQL/Kafka) and the error type (timeout/refused/auth/5xx)
2. Verify pod health + whether endpoints look correct
3. Only then choose: restart/scale/shift traffic (`#MANUAL`)

## Minimal K8s Checks (Works for Most DBs)
```bash
kubectl get pod -A | grep -iE 'yugabyte|clickhouse|mysql|kafka'
kubectl get svc -A | grep -iE 'yugabyte|clickhouse|mysql|kafka'
kubectl get endpoints -A | grep -iE 'yugabyte|clickhouse|mysql|kafka'
```

## First-Line Decision Branches
- Endpoints empty: suspect selector/readiness/operator gating first.
- Pods Running but clients fail: check bind/listen, ingress/LB path, and node-level networking.
- spikes/lags: stop the bleeding first (rate limit/degrade/shift traffic), then do a deep RCA.

## Further Reading (Deep Doc)
- Full reference: [reference-db-issue-quick-reference.md](./reference-db-issue-quick-reference.md)
