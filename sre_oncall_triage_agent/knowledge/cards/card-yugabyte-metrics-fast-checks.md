---
metadata:
  kind: reference
  status: draft
  summary: "Card: Yugabyte metrics quick checks - which /metrics to curl, and which signals to watch during an incident."
  tags: ["card", "yugabyte", "monitoring", "metrics", "debugging", "oncall"]
  first_action: "Curl /metrics from one tserver and one master first"
---

# Card: Yugabyte Metrics - Quick Checks

## TL;DR (Do This First)
1. Curl `/metrics` from one master and one tserver
2. Look for signals like overload / raft catch-up / latency
3. Before touching the cluster, decide if you need to reduce blast radius (traffic/MM) (`#MANUAL`)

## Minimal Commands
```bash
curl -m 2 http://<master-ip>:7000/metrics | head
curl -m 2 http://<tserver-ip>:9100/metrics | head
```

## Further Reading (Deep Doc)
- Full reference: [reference-yugabyte-monitoring-commands-reference.md](./reference-yugabyte-monitoring-commands-reference.md)
