---
metadata:
  kind: reference
  status: draft
  summary: "Card: FP service infra quick entrypoints (where to look first for FP/FP-Async/FP-Cron, and where Kafka/DB dependencies sit and how to start triage)."
  tags: ["card", "fp", "service", "infra", "kafka", "yugabyte", "clickhouse", "mysql", "oncall"]
  first_action: "Confirm cluster/env first, then check FP and dependency health"
---

# Card: FP Infra - Quick Entrypoints

## TL;DR (Do This First)
1. Confirm the target env/cluster (avoid debugging the wrong environment)
2. Snapshot: FP pods + restarts + nodes
3. Identify involved dependencies: Kafka vs DB vs ingress

## Minimal Snapshot
```bash
kubectl get pod -n pci -o wide | grep -iE 'fp-|fp_' || true
kubectl get deploy -n pci | grep -i fp || true
kubectl get sts -n pci | grep -i mysql || true
```

## Dependency Quick Map
- FP realtime path: ingress/gateway -> FP -> DB
- FP-Async path: Kafka -> FP-Async -> DB/ClickHouse (depends on the pipeline)

## When You See...
- QPS spike / 429: check ingress rate-limit window + burst first; stop the bleeding before scaling, avoid unbounded scale-out.
- Lag spike: check downstream sink pressure (ClickHouse parts/merge) first, then consider scaling consumers.
- DB saturation: scale/relieve the DB first; scaling FP when the DB has no headroom can amplify the incident.

## Further Reading (Deep Doc)
- Full reference: [reference-fp-service-infra-reference.md](./reference-fp-service-infra-reference.md)
