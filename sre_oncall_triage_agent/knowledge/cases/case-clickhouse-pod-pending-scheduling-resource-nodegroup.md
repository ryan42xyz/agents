---
metadata:
  kind: case
  status: final
  summary: "Troubleshooting ClickHouse StatefulSet pods stuck in Pending after increasing resources: scheduler events usually show insufficient resources plus overly narrow nodeSelector/affinity constraints; fix by aligning pod requests to node allocatable or expanding/switching the dedicated node group while keeping labels/taints compatible."
  tags: [clickhouse, kubernetes, scheduling, pending, resources, nodegroup, node-selector, affinity, aws, asg]
  first_action: "Describe the Pending pod and record scheduler events"
  related:
    - ./case-clickhouse-pod-pending-scheduling-resource-nodegroup.incident.md
    - ./checklist-cluster-troubleshooting-checklist.md
    - ./card-kubectl-describe-node-key-signals.md
    - ./card-k8s-resource-pressure-fast-mitigation.md
    - ./runbook-k8s-pod-pending-asg-cluster-autoscaler.md
---

# ClickHouse Pod Pending: Scheduling Failure After Resource Increase

## TL;DR (Do This First)
1. Run `kubectl -n <ns> describe pod <pod>` and copy the Scheduling events (focus on `Insufficient cpu/memory` and `didn't match Pod's node affinity/selector`).
2. Confirm whether the workload is pinned (e.g., `nodeSelector: dedicated-node=true`), and list the nodes that actually match.
3. Compare `pod requests` vs `node allocatable` (allocatable is always smaller than the instance spec).
4. Fix paths:
   - If requests > allocatable of the dedicated node group: expand/switch to a larger dedicated node group (bigger instance type) or lower pod requests.
   - If larger nodes exist but are excluded by labels/taints: fix labels/taints/tolerations so the scheduler can use them.

## Core Troubleshooting Chain

```text
Pod Pending
  -> kubectl describe pod (Events)
  -> Determine which gate failed
     A) Insufficient cpu/memory
        -> pod requests > node allocatable (instance capacity)
     B) NotTriggerScaleUp / max node group size reached
        -> nodegroup/ASG at max; autoscaler will not add nodes
     C) didn't match node affinity/selector / taints not tolerated
        -> workload is pinned; eligible nodegroup is narrower than you think
  -> Identify the intended nodegroup for this pod
     - nodeSelector / nodeAffinity (labels)
     - tolerations (match node taints; often how nodegroups are isolated)
  -> Fix
     - If it cannot fit: lower requests or create/switch to a larger dedicated nodegroup (keep labels/taints compatible)
     - If it can fit but cannot scale: raise nodegroup max or add a new nodegroup/ASG (keep labels/taints compatible)
     - If it can fit and exists but excluded: fix labels/taints/tolerations/affinity
```

## Safety Boundaries
- Read-only: `kubectl get/describe`, view node labels/taints, view requests/limits.
- `#MANUAL`: modify StatefulSet resources, modify node labels/taints, create/update ASG/node groups, scale node groups.

## Publish Readiness (Why This Is Final)
This is a production-grade, reusable scheduling playbook. It intentionally avoids environment-specific identifiers; the incident file holds the environment details, while this case preserves only the decision logic and verifiable gates.



## Related
- [case-clickhouse-pod-pending-scheduling-resource-nodegroup.incident.md](./case-clickhouse-pod-pending-scheduling-resource-nodegroup.incident.md)
- [checklist-cluster-troubleshooting-checklist.md](./checklist-cluster-troubleshooting-checklist.md)
- [card-kubectl-describe-node-key-signals.md](./card-kubectl-describe-node-key-signals.md)
- [card-k8s-resource-pressure-fast-mitigation.md](./card-k8s-resource-pressure-fast-mitigation.md)

## Symptoms
- ClickHouse StatefulSet pod stays `Pending` after increasing resources.
- `kubectl describe pod` shows one or both:
  - `Insufficient cpu` / `Insufficient memory`
  - `node(s) didn't match Pod's node affinity/selector`

## Investigation (Standard Path)

### 1) Confirm the scheduler reason (events)

```bash
kubectl -n <ns> describe pod <pod>
```

Record:
- requested CPU/memory
- nodeSelector / affinity constraints
- exact Scheduling events

Event keywords to look for (copy the exact lines):
- `FailedScheduling`
- `Insufficient cpu` / `Insufficient memory`
- `didn't match Pod's node affinity/selector`
- `NotTriggerScaleUp`
- `max node group size reached`

### 2) Check scheduling constraints (where can it land?)

Focus on:
- `spec.nodeSelector`
- `spec.affinity.nodeAffinity`
- `spec.tolerations` vs node taints

Commands:

```bash
kubectl get pod -n <ns> <pod> -o yaml
kubectl get nodes --show-labels
kubectl describe node <node>
```

Quick mapping trick (pod -> taint/label -> nodegroup):

```bash
# Pod tolerations (often the nodegroup isolation mechanism)
kubectl get pod -n <ns> <pod> -o jsonpath='{.spec.tolerations}'

# Candidate nodes by label (if you have a dedicated label)
kubectl get nodes -l dedicated-node=true -o wide
```

Rule of thumb:
- If `nodeSelector` is strict (e.g., `dedicated-node=true`), even larger nodes in the cluster will not be candidates if they do not have the label.

### 3) Check resource feasibility (requests vs allocatable)

Even if the instance spec says "8 vCPU / 64GB", Kubernetes `allocatable` is usually smaller (kube/system reserved + eviction thresholds).

Scheduling compares `requests` (not `limits`) against node `allocatable`.

Commands:

```bash
kubectl describe node <candidate-node>
kubectl top node <candidate-node>

# Pod requests (what the scheduler uses)
kubectl get pod -n <ns> <pod> -o jsonpath='{.spec.containers[*].resources.requests}'
```

Decision:
- If `pod.request.cpu > node.allocatable.cpu` or `pod.request.memory > node.allocatable.memory`, it cannot be scheduled onto that node group.

### 4) Investigate "larger nodes exist but are excluded"

If another node group has enough allocatable but lacks required labels (or has incompatible taints), the scheduler will still reject it.

Common mismatches:
- Dedicated label missing: pod requires `dedicated-node=true`, nodes do not have it
- Taint mismatch: nodes tainted `dedicated=clickhouse:NoSchedule` but pod has no matching toleration

## Mitigation Options

### Option A: Align pod requests to the current dedicated node group
- Reduce requests to fit `allocatable` (not instance spec).
- Keep some headroom for system daemons and operator sidecars.

### Option B: Expand/switch the dedicated ClickHouse node group
- Create/resize a dedicated node group with larger instance type.
- Preserve bootstrap node labels (example):

```text
--node-labels=dedicated-node=true
```

- Verify taints and pod tolerations remain compatible.

Example (AWS ASG) command chain to clone an existing dedicated ASG into a larger one (manual, environment-specific):

```bash
#MANUAL
# 1) Inspect the existing ASG launch template reference
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names <asg-name> \
  --query "AutoScalingGroups[0].LaunchTemplate"

# 2) Fetch the latest launch template data (edit instance type inside template.json as needed)
aws ec2 describe-launch-template-versions \
  --launch-template-name <launch-template-name> \
  --versions '$Latest' \
  --query 'LaunchTemplateVersions[0].LaunchTemplateData' \
  > template.json

# 3) Create a new launch template for the larger instance type
aws ec2 create-launch-template \
  --launch-template-name <new-launch-template-name> \
  --launch-template-data file://template.json

# 4) Reuse the same subnets/VPCZoneIdentifier as the old ASG
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names <asg-name> \
  --query "AutoScalingGroups[0].VPCZoneIdentifier"

# 5) Create the new ASG (ensure autoscaler discovery tags match your cluster)
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name <new-asg-name> \
  --launch-template LaunchTemplateName=<new-launch-template-name>,Version='$Latest' \
  --min-size 0 \
  --max-size 1 \
  --desired-capacity 1 \
  --vpc-zone-identifier subnet-<redacted> \
  --tags Key=k8s.io/cluster-autoscaler/enabled,Value=true,PropagateAtLaunch=true \
         Key=k8s.io/cluster-autoscaler/<cluster-name>,Value=owned,PropagateAtLaunch=true
```

Notes:
- Keep node labels/taints consistent with what the pod requires, otherwise the new capacity will not be eligible.
- `template.json` usually needs an explicit instance type change; do not assume it is correct without reviewing.

### Option C: Relax/adjust scheduling constraints (only if acceptable)
- Expand nodeSelector/affinity to include the larger node group.
- Or label the larger node group to join the dedicated pool.

## Verification
- The Pending pod becomes scheduled: `kubectl get pod -n <ns> -o wide` shows a node name.
- ClickHouse pod enters `Running` and becomes Ready.
- No unintended workloads get pulled onto dedicated nodes (validate labels/taints strategy).

Recommended production thresholds (to reduce regressions):
- Pod scheduling: `Pending` -> `Running` within `<SLO_minutes>` after capacity/constraint fix.
- Stability window: no new ClickHouse pods stuck `Pending` for `>= 30m`.
- Capacity sanity: candidate nodes keep `>= <headroom_percent>%` allocatable headroom after scheduling (avoid sizing exactly at allocatable).

## Closeout
- Done when ClickHouse pods are stable and no new pods are stuck Pending due to the same constraints.

Closeout checklist (production):
- Record the exact `FailedScheduling` event lines (redact cluster/node IDs).
- Record the requests/allocatable comparison that proves feasibility.
- Record every `#MANUAL` change (who/when/what) and the rollback plan:
  - If you created a new node group: rollback is scaling it to 0 (after migration) and removing labels/taints discovery if needed.
  - If you relaxed affinity/labels: rollback is restoring the previous selector/affinity and validating no workload drift.

## Evidence Snippets (Sanitized Examples)

Scheduler events excerpt (from `kubectl describe pod`):

```text
Warning  FailedScheduling  <time>  default-scheduler  0/<N> nodes are available: <n1> Insufficient cpu, <n2> Insufficient memory, <n3> node(s) didn't match Pod's node affinity/selector.
Normal   NotTriggerScaleUp <time>  cluster-autoscaler  pod didn't trigger scale-up: <reason> (e.g., max node group size reached)
```

Allocatable vs requests feasibility example:

```text
pod requests: cpu=<pod_cpu>, memory=<pod_mem>
node allocatable (candidate pool): cpu=<alloc_cpu>, memory=<alloc_mem>
decision: schedulable only if requests <= allocatable with headroom
```

## One-line Essence
- After increasing resources, requests exceeding node allocatable will directly cause scheduling failure, and nodeSelector/affinity may prevent falling back to other node groups.
