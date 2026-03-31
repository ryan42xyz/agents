---
metadata:
  kind: runbook
  status: draft
  summary: "YugabyteDB debug quickstart notes: how to reach the tserver Web UI (9000) via node IP and common port mapping (9100 RPC, 12000 YCQL, 5433 YSQL), plus steps to validate reachability using `ss` and local `curl` without relying on a browser."
  tags: ["yugabyte", "debugging", "ports", "tserver"]
  first_action: "Check listening ports via `ss -lntp | grep yb-tserver`"
---

# YugabyteDB Debug Quickstart

## TL;DR (Do This First)
1. On the node, confirm yb-tserver is listening: `ss -lntp | grep yb-tserver`
2. Identify the Web UI port (commonly 9000) and test locally: `curl -sS http://127.0.0.1:9000/ | head`
3. If testing from another host, validate network path and security rules before blaming Yugabyte

## Stop / Escalate When
- You suspect data loss / corruption, or the cluster is flapping
- You need to restart Yugabyte processes or change resource limits/config (`#MANUAL`)
- Connectivity issues point to network policy / security group / firewall changes (`#MANUAL`)

## Exit Criteria
- You can reach tserver Web UI (9000) and/or required client ports (YCQL/YSQL)
- You have a clear classification: Yugabyte process down vs network blocked vs overload

## Common Ports (typical)
- 9000: tserver Web UI
- 9100: RPC
- 12000: YCQL
- 5433: YSQL

## Notes / Links
- https://chatgpt.com/c/694bd80e-c608-8327-a601-19a66282ae09
- Example utilz: `http://<node-ip>:9000/utilz`
