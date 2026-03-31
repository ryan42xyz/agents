---
metadata:
  kind: runbook
  status: draft
  summary: "Card: K8s resource pressure (DiskPressure/CPU/Memory) fast mitigation: minimal safe commands and decision boundaries."
  tags: ["card", "k8s", "diskpressure", "cpu", "memory", "oncall"]
  first_action: "Use node Conditions/Events to identify pressure type first"
---

# Card: K8s Resource Pressure - Fast Mitigation

## TL;DR (Do This First)
1. Confirm pressure type: `kubectl describe node` -> `Conditions` + `Events`
2. Decide: *clean up* vs *migrate workloads* vs *replace the node* (in ASG setups, replacing the node is often the most stable stop-the-bleeding move)
3. Verify: pressure is gone and no more evictions for 15-30 minutes

## DiskPressure (ephemeral-storage) - Key Signals
- `DiskPressure=True`
- Events: `EvictionThresholdMet`, `ImageGCFailed`, `FreeDiskSpaceFailed`
- Symptoms: pods `Evicted`, new pods stuck `ContainerCreating`/`ImagePullBackOff`

## MemoryPressure / CPU Saturation - Key Signals
- `MemoryPressure=True`, OOMKills, kernel OOM, frequent restarts
- CPU pinned + kubelet slow, probes time out, scheduling latency

## Minimal Commands
```bash
kubectl describe node <node>
kubectl get pod -A -o wide | grep " <node>$"
kubectl top node <node>

# For eviction evidence
kubectl get events -A --sort-by=.lastTimestamp | tail -n 50
```

## Decision Rules (Practical)
- If `ImageGCFailed` keeps happening: do not get stuck in endless cleanup; replace the node (`#MANUAL`).
- If only one node is bad: cordon/drain + replace is usually lower risk than changing cluster-level config (`#MANUAL`).
- If it is systemic pressure (many nodes): treat it as a capacity incident; scale the nodegroup or reduce load.

## Manual Actions (Boundary)
```bash
#MANUAL
kubectl cordon <node>
kubectl drain <node> --ignore-daemonsets --delete-local-data
```

## Verification
- Node condition returns to normal (e.g., `DiskPressure=False`)
- No new `Evicted` for the same reason

## Further Reading (Deep Doc)
- Full runbook: [runbook-k8s-resource-exhaustion.md](./runbook-k8s-resource-exhaustion.md)
