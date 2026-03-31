---
metadata:
  kind: case
  status: final
  summary: "Oncall: many pods get Evicted due to node DiskPressure (ephemeral-storage); quickly confirm via node/pod describe events (ImageGCFailed/EvictionThresholdMet), and in an ASG worker pool the fastest stopgap is cordon/drain plus node replacement."
  tags: ["k8s", "pod", "evicted", "diskpressure", "asg"]
  first_action: "Describe the pod/node to confirm DiskPressure eviction"
  related:
    - ./case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.incident.md
    - ./card-k8s-resource-pressure-fast-mitigation.md
    - ./card-kubectl-describe-node-key-signals.md
---

# Oncall Case: Pod Evicted (DiskPressure) + Fast Mitigation on ASG Workers

## TL;DR (Do This First)
1. Confirm eviction reason: `kubectl describe pod <pod>` -> `[DiskPressure]`
2. Confirm node condition/events: `kubectl describe node <node>` (ImageGCFailed / EvictionThresholdMet)
3. Fast mitigation in ASG: cordon/drain + replace the node (`#MANUAL`)

## Safety Boundaries
- Read-only: describe/logs/usage
- `#MANUAL`: cordon/drain, replace nodes, delete container images/logs



## Related
- [case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.incident.md](./case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.incident.md)
- [card-k8s-resource-pressure-fast-mitigation.md](./card-k8s-resource-pressure-fast-mitigation.md)
- [card-kubectl-describe-node-key-signals.md](./card-kubectl-describe-node-key-signals.md)

## Triage
- Confirm it is eviction (not app crash): `kubectl describe pod <pod>` shows `Reason: Evicted` and the message contains `[DiskPressure]`
- Identify the node and confirm conditions/events: `kubectl describe node <node>` (EvictionThresholdMet / NodeHasDiskPressure / ImageGCFailed)
- Fast path for ASG: when GC fails, prefer cordon/drain and replace the node instead of repeated cleanup (`#MANUAL`)
- If you must inspect the node: check `df -h` / `df -i`, and large directories under `/var/lib/containerd`, `/var/lib/kubelet`, `/var/log`

## Decision

- Prefer "replace the node" over repeated cleanup on the same node: when `ImageGCFailed/FreeDiskSpaceFailed` appears and DiskPressure keeps recurring, these nodes often cannot reliably self-heal.

## Verification

- Node condition returns to healthy: `DiskPressure=False` (on a stable node)
- Workloads reschedule and stay stable; `kubectl get pods -n prod` stops producing new `Evicted`

## Closeout

- Done when alerts clear and the cluster stays stable for 15-30 minutes (no new `Evicted` due to DiskPressure)
- Done when the problematic node is drained/replaced (or confirmed healthy) and scheduling is back to normal

## One-line Essence
- In an ASG-managed worker pool, the fastest reliable fix for DiskPressure eviction is cordon/drain and replace the node.

## Symptoms

- You will see many pods in `Evicted` under `kubectl get pod -n <ns>` (e.g., `<cron-deployment>-...`).
- `kubectl -n prod describe pod <pod>` shows:
  - `Reason: Evicted`
  - `Message: Pod was rejected: The node had condition: [DiskPressure].`

This is usually not an app crash. It is the kubelet eviction manager evicting pods to protect the node when disk/ephemeral-storage pressure exceeds thresholds.

## Fast Troubleshooting Path (By Priority)

### 1) Classify the eviction reason via the pod message

```bash
kubectl -n prod describe pod <pod>
```

If `Message` clearly contains `[DiskPressure]`, go straight to node-level checks; do not start from application logs.

### 2) Check node events; confirm ephemeral-storage pressure

```bash
kubectl describe node <node>
```

Key events (typical signatures):

- `EvictionThresholdMet: Attempting to reclaim ephemeral-storage`
- `ImageGCFailed` / `FreeDiskSpaceFailed: Failed to garbage collect required amount of images ... only found 0 bytes eligible to free`
- `NodeHasDiskPressure`

Explanation:

- After kubelet detects ephemeral-storage eviction thresholds, it attempts to reclaim space via image GC.
- If there is nothing eligible to reclaim (images in use/too new/already cleaned), GC fails and eviction continues; pods get Evicted/Rejected.

### 3) Node-side checks (block space vs inode)

Even if `df -h` shows free space, DiskPressure can still happen, for example:

- A short burst fills the disk (temp files/logs/image pulls) and then drops, but eviction has already started; or
- Inode exhaustion (too many small files); or
- Eviction thresholds are computed based on imagefs/nodefs partitions and reserved space.

Recommended to run on the node:

```bash
df -h
df -i

# Focus on containerd/kubelet/log usage
sudo du -xh /var/lib/containerd /var/lib/kubelet /var/log 2>/dev/null | sort -h | tail -n 50

# Container runtime images/containers
sudo crictl images
sudo crictl ps -a
```

## Fastest Reliable Fix (Conclusion for This Case)

Because workers are managed by ASG: after draining the problematic node, ASG replaces it with a clean new node (clean disk, no pressure), restoring scheduling quickly.

### Mitigation steps

1) Stop scheduling onto the bad node:

```bash
#MANUAL
kubectl cordon <node>
```

2) Evict workloads (let the scheduler/ASG move pods to healthy/new nodes):

```bash
#MANUAL
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
```

Notes:

- `--ignore-daemonsets` avoids getting stuck on DaemonSets.
- `--delete-emptydir-data` deletes local `emptyDir` data; assess impact for workloads that rely on local temporary data.

If the node is already `NotReady`, `drain` may fail or hang. In an ASG environment, stick to the "replace the node" approach (e.g., terminate the EC2 so ASG launches a new instance).

### When this is the best option

- DiskPressure keeps recurring, and `ImageGCFailed/FreeDiskSpaceFailed` indicates it is hard to self-heal.
- Root disk is small (e.g., ~50G), but the node hosts multiple large-image workloads, repeatedly triggering eviction thresholds.
- Workloads can be migrated safely (enough replicas, sane PDBs).

## Prevention / Long-term Improvements

- Capacity: increase worker root volume; leave buffer for imagefs/nodefs watermarks.
- Workload hygiene: set `ephemeral-storage` requests/limits for disk-writing pods; ensure log rotation.
- Image hygiene: reduce large image churn/co-location; avoid burst-pulling multiple huge images on one node.
- Observability: add alerts/dashboards for `NodeHasDiskPressure`, `EvictionThresholdMet`, `ImageGCFailed`.

## Avoid Leaking Sensitive Data in Outputs

`kubectl describe pod` may contain plaintext env vars (e.g., DB passwords). Before pasting into tickets/chat, redact sensitive parts or share only the `Reason/Message/Events` lines.
