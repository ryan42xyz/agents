---
metadata:
  kind: runbook
  status: draft
  summary: "Card: Yugabyte quick debugging - common ports, first commands, and minimal reachability checks without relying on the UI."
  tags: ["card", "yugabyte", "debugging", "ports", "tserver", "ysql", "ycql", "oncall"]
  first_action: "Check listen ports and basic /metrics reachability first"
---

# Card: Yugabyte Quick Debugging (Ports + Commands)

## TL;DR (Do This First)
1. Pick a tserver/master endpoint
2. Verify the ports are listening (`ss`) and basic HTTP endpoints respond
3. Only then discuss balancing/recovery

## Common Ports (Environment-Dependent)
- tserver UI: `9000`
- tserver RPC: `9100`
- YCQL: `9042` or `12000`
- YSQL: `5433`

## Minimal Commands
```bash
ss -lntp | grep -i yb || true
curl -m 2 http://<tserver-ip>:9000/ | head
curl -m 2 http://<tserver-ip>:9100/metrics | head
```

## Further Reading (Deep Doc)
- Full runbook: [runbook-yugabyte-debug-process.md](./runbook-yugabyte-debug-process.md)
