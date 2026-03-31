---
metadata:
  kind: runbook
  status: draft
  summary: "Card: ClickHouse disk/PVC/EBS space exhaustion quick triage - minimal checks and stop-the-bleeding actions (manual boundary)."
  tags: ["card", "clickhouse", "storage", "disk", "pvc", "ebs", "oncall"]
  first_action: "Check PVC status first, then run df inside the pod"
---

# Card: ClickHouse Space Exhaustion - Quick Triage

## TL;DR (Do This First)
1. Confirm the failure layer: PVC Pending? volume full? node pressure?
2. Snapshot: pod status + PVC + `df -h` inside the pod
3. Stabilize: restore writes safely (usually requires `#MANUAL`)

## Minimal Commands
```bash
kubectl get pod -n <ns> | grep -i clickhouse
kubectl get pvc -n <ns>
kubectl exec -n <ns> <ch-pod> -- df -h
```

## Further Reading (Deep Doc)
- Full runbook: [runbook-clickhouse-disk-space-exhaustion.md](./runbook-clickhouse-disk-space-exhaustion.md)
