---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md
  title: "Kubernetes Pods Evicted Due to Node DiskPressure (ASG Workers)"
  summary: "A pod eviction incident: worker nodes hit DiskPressure (ephemeral-storage); kubelet eviction plus ImageGCFailed caused many pods to be Evicted; in an ASG fleet the fastest mitigation is cordon/drain and replace nodes; includes a prevention checklist."
  tags: [kubernetes, eviction, diskpressure, ephemeral-storage, asg, containerd]
  patterns: [k8s-diskpressure-eviction, image-gc-failed-node-replace]
---

# Incident: Kubernetes Pods Evicted Due to Node DiskPressure (ASG Workers)

## 1. Incident Overview
- Date: TBD
- Severity: TBD
- Duration: TBD
- System: Kubernetes cluster with ASG-managed worker nodes
- Impact: `prod` namespace saw many pods in `Evicted` / rejected scheduling due to node `[DiskPressure]` (exact blast radius: TBD)

## 2. System Context
- Architecture (relevant): Scheduler -> worker nodes -> kubelet eviction manager (ephemeral-storage)
- Key dependency: node disk (imagefs/nodefs) health governs scheduling/eviction behavior
- Scale: TBD

## 3. Environment
- Cloud: AWS (ASG mentioned; exact cluster/region: TBD)
- Platform: Kubernetes
- Container runtime: containerd (tools referenced: `crictl`)
- Namespaces: `prod`

## 4. Trigger
- Trigger: operator noticed mass `Evicted` in `kubectl get pod -n prod`

## 5. Impact Analysis
- Blast radius: node-level; affects any pod scheduled to impacted workers
- User-visible symptoms: TBD
- Data loss: TBD (some workloads may lose `emptyDir` data if drained)
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: describe/logs/usage
- `#MANUAL`: cordon/drain, node replacement, deleting container images/logs
- Sharing hygiene: `kubectl describe pod` output can include plaintext env vars; only copy `Reason/Message/Events` after redaction

## 7. Investigation Timeline
- Confirm pod eviction reason:
  - `kubectl -n prod describe pod <pod>` -> `Reason/Message`
- Confirm node condition + events:
  - `kubectl describe node <node>` -> `NodeHasDiskPressure`, `EvictionThresholdMet`, `ImageGCFailed/FreeDiskSpaceFailed`
- Validate node storage (block vs inode):
  - `df -h`, `df -i`
  - inspect heavy paths: `/var/lib/containerd`, `/var/lib/kubelet`, `/var/log`
  - runtime inventory: `crictl images`, `crictl ps -a`

## 8. Root Cause
- Root cause: worker node(s) crossed kubelet eviction thresholds for ephemeral storage; image GC could not reclaim space (`0 bytes eligible to free`), so `DiskPressure` persisted and eviction continued.
- Symptom vs root cause:
  - Symptom: pods show `Evicted` / rejected due to `[DiskPressure]`
  - Root cause: node ephemeral-storage pressure + image GC failure prevented self-recovery

## 9. Mitigation
- Fast mitigation in ASG: cordon/drain impacted node(s), then replace node (e.g., terminate the unhealthy instance so ASG launches a clean node) (`#MANUAL`).
- Verification:
  - Node condition becomes `DiskPressure=False`
  - `kubectl get pods -n prod` stops producing new `Evicted`

## 10. Prevention / Improvement
- Short-term:
  - Alert on `NodeHasDiskPressure`, `EvictionThresholdMet`, `ImageGCFailed`
  - Ensure safe PDB/replicas so draining is feasible
- Long-term:
  - Increase worker root volume / leave buffer for imagefs/nodefs
  - Enforce `ephemeral-storage` requests/limits for disk-writing pods
- Reduce image churn and large image co-location; validate log rotation (container logs/journald)

## 11. Generalizable Lessons
- Always read `kubectl describe pod` `Reason/Message` first; don't start with app logs for eviction incidents.
- For node pressure, `kubectl describe node` events are the highest-signal artifact.
- Disk troubleshooting must check both blocks and inodes (`df -h` + `df -i`).
- In ASG fleets, persistent DiskPressure + ImageGCFailed often warrants node replacement rather than repeated manual cleanup.
- Pattern Card:
  - Pattern name: k8s-diskpressure-eviction
  - When it happens: node ephemeral-storage crosses eviction thresholds
  - Fast detection signals: `Reason: Evicted`, node `NodeHasDiskPressure`, `ImageGCFailed`
  - Fast mitigation: cordon/drain + replace node
- Common pitfalls: chasing app logs; not checking inodes; draining without understanding `--delete-emptydir-data`

## Tags & Patterns
- Tags: kubernetes, eviction, diskpressure, ephemeral-storage, asg, containerd
- Patterns: k8s-diskpressure-eviction, image-gc-failed-node-replace
- First Action: `kubectl -n prod describe pod <pod>` and confirm `[DiskPressure]`

## Evidence Mapping
- Trigger -> "`kubectl get pod -n prod` shows a large number of pods in `Evicted`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Pod reason -> "`Reason: Evicted`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Pod message -> "`Message: Pod was rejected: The node had condition: [DiskPressure].`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Node event -> "`EvictionThresholdMet: Attempting to reclaim ephemeral-storage`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Node event -> "`ImageGCFailed` / `FreeDiskSpaceFailed: Failed to garbage collect required amount of images ... only found 0 bytes eligible to free`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Node condition -> "`NodeHasDiskPressure`" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Decision -> "Prefer node replacement over repeated manual cleanup on the unhealthy node" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Triage)
- Mitigation -> "Fast mitigation in ASG: cordon/drain + replace node (`#MANUAL`)" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:TL;DR)
- Verification -> "- Node becomes `DiskPressure=False`, and workloads resume scheduling after a clean node joins" (case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md:Verify)
