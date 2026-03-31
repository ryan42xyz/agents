---
metadata:
  kind: reference
  status: draft
  summary: "Card: Understand `kubectl describe node` in 2 minutes (only the key parts: Conditions/Events/Allocatable/Taints/Top pods), and decide the next oncall action quickly."
  tags: ["card", "k8s", "node", "kubectl", "oncall"]
  first_action: "Look at Conditions + Events first, then Allocatable vs Requests"
---

# Card: kubectl describe node - Only Key Signals

## TL;DR (Do This First)
1. `Conditions` + `Events` (copy the few lines that explain *why now*)
2. `Taints` + `Unschedulable` (can the node still accept pods?)
3. `Capacity/Allocatable` vs `Allocated resources` (is there scheduling headroom?)
4. `Non-terminated Pods` table: who is consuming CPU/memory on this node?

## What To Copy From The Output
When writing the incident note, do not paste the entire output; only copy:
- Node name + instance type (find it in `Labels`)
- `Conditions` table (the 5-10 line block)
- Last 20-50 lines of `Events` (if present)
- `Allocatable` and `Allocated resources` summary
- First 5 lines of `Non-terminated Pods` (largest requests/limits)

## Quick Decision Table

| Signal You See | Meaning | Next Step |
|---|---|---|
| `Ready=False` | kubelet/node-level failure | Follow Node NotReady flow; cordon/drain if needed (`#MANUAL`) |
| `DiskPressure=True` | ephemeral-storage pressure | Use the resource pressure flow; in ASG setups, replacing the node is often the fastest stabilization (`#MANUAL`) |
| `MemoryPressure=True` | memory pressure/eviction risk | Find top pods; reduce load or migrate (`#MANUAL`) |
| `NetworkUnavailable=True` | CNI/routing issue | Treat as node networking failure; compare across nodes |
| `Events: ImageGCFailed/FreeDiskSpaceFailed` | pressure will not self-heal | Do not get stuck in repeated cleanup; replace the node (`#MANUAL`) |
| `Allocated cpu` ~ 95-100% | scheduling can fail even if Ready | adjust requests / scale nodegroup / migrate workloads |
| `Taints` are strict with no matching tolerations | pods will stay Pending | fix tolerations/taints/labels (`#MANUAL`) |

## Minimal Commands
```bash
# Node snapshot
kubectl describe node <node>

# Quick pods-on-node view
kubectl get pod -A -o wide | grep " <node>$"

# Resource pressure signals
kubectl top node <node>
kubectl top pod -A --sort-by=memory | head
kubectl top pod -A --sort-by=cpu | head
```

## Common Pitfalls
- Using `Capacity` instead of `Allocatable` to infer schedulable headroom.
- Assuming the node is healthy when you see `Events: <none>`; pressure may not emit events.
- Pasting huge outputs into tickets; the truly key lines get buried.

## Further Reading (Deep Doc)
- Full walkthrough with examples: [reference-kubectl-describe-node-analysis.md](./reference-kubectl-describe-node-analysis.md)
