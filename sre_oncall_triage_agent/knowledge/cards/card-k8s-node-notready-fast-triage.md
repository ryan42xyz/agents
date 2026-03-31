---
metadata:
  kind: runbook
  status: draft
  summary: "Card: Node NotReady quick triage - what to check first, and what evidence to capture before any manual action."
  tags: ["card", "k8s", "node", "notready", "kubelet", "oncall"]
  first_action: "Run describe node and copy Conditions+Events"
---

# Card: Node NotReady - Quick Triage

## TL;DR (Do This First)
1. Find affected nodes: `kubectl get nodes`
2. Snapshot: `kubectl describe node <node>` (Conditions + Events)
3. Check blast radius: pods on that node
4. Manual actions (cordon/drain/replace) are all `#MANUAL`

## Minimal Commands
```bash
kubectl get nodes
kubectl describe node <node>
kubectl get pod -A -o wide | grep " <node>$"
```

## Evidence You Need
- Which condition flipped, and when (`LastTransitionTime`)
- Events related to kubelet/runtime/network/disk pressure
- Whether it is a single-node issue or a wider issue

## Further Reading (Deep Doc)
- Full runbook: [runbook-k8s-node-notready-runbook.md](./runbook-k8s-node-notready-runbook.md)
