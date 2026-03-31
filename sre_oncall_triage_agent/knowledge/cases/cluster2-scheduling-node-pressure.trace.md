---
metadata:
  kind: structured-triage-trace
  status: final
  sources:
    - case-clickhouse-pod-pending-scheduling-resource-nodegroup.md
    - case-k8s-pod-evicted-diskpressure-asg-fast-mitigation.md
    - case-aws-asg-scale-out-node-join-failure.md
    - case-spark-job-pending-not-running.md
  schema_version: "0.1"
  tags: ["kubernetes", "scheduling", "pending", "eviction", "diskpressure", "asg", "node"]
  failure_domain: "scheduling / node capacity"
  cluster: "Cluster 2 — Scheduling, capacity, node pressure"
---

# Structured Triage Trace: Cluster 2 — Scheduling / Node Pressure

---

## Signal

```
signals:
  A  pod Pending / FailedScheduling
  B  pod Evicted + DiskPressure condition on node
  C  ASG scale-out instances not joining cluster
  D  Spark/batch job stuck in Pending, never reaches Running

→ cluster: Cluster 2 (Scheduling / Node Capacity)
→ reason:  all four share the same root question:
           "why can't this workload land on a healthy node?"
```

### Routing Logic

```
IF   pod_status == Pending AND events contain FailedScheduling
THEN triage_path = scheduling_constraint_analysis
     first_action = kubectl describe pod → read scheduler events

IF   pod_status == Evicted AND node_condition contains DiskPressure
THEN triage_path = node_disk_pressure
     first_action = kubectl describe node → confirm eviction reason

IF   asg_scaling AND node NOT in kubectl get nodes
THEN triage_path = node_join_failure
     first_action = check ASG activity history → instance lifecycle stage

IF   job_status == Pending AND never reaches Running
THEN triage_path = job_resource_or_pool_stuck
     first_action = get job_id → confirm pods stuck → terminate + recycle
```

---

## Decision Trace — Branch A: Pod Pending / FailedScheduling

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Describe pending pod | `kubectl describe pod <pod>` | Scheduler events: "Insufficient cpu/memory" or "didn't match node affinity" | Resource gap or placement constraint mismatch | 0.90 |
| 2 | Identify intended node group | Pod spec: nodeSelector + tolerations + affinity | Workload pinned to dedicated nodegroup via label/taint | Eligible node pool is narrower than assumed | 0.85 |
| 3 | Check node allocatable vs pod requests | `kubectl describe node` → Allocatable section | Pod requests > node allocatable (instance spec ≠ allocatable) | Need larger node type OR lower requests | 0.90 |
| 4 | Check ASG max size | AWS console / `aws autoscaling describe` | ASG at max, autoscaler not triggering scale-out | Cannot add nodes; scheduling blocked | 0.85 |

**Branch A fix paths:**
```
requests > allocatable  → expand node group to larger instance type (#MANUAL)
affinity/taint mismatch → fix labels/taints/tolerations (#MANUAL)
ASG at max              → raise max size or add new nodegroup (#MANUAL)
```

---

## Decision Trace — Branch B: Pod Evicted / DiskPressure

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Confirm eviction reason | `kubectl describe pod <pod>` | `Reason: Evicted`, message: `[DiskPressure]` | Node hit ephemeral-storage eviction threshold | 0.95 |
| 2 | Confirm node condition | `kubectl describe node <node>` | `NodeHasDiskPressure=True`, `ImageGCFailed` | kubelet tried to GC images but couldn't free enough space | 0.90 |
| 3 | Check disk usage on node | `df -h` on node | `/var/lib/containerd` or `/var/log` near full | Container layer or log accumulation is the culprit | 0.85 |
| 4 | Assess recovery path | Is GC cycling and failing repeatedly? | Yes: `ImageGCFailed` repeated | Node cannot self-heal; replace preferred over cleanup | 0.90 |

**Branch B fix path:**
```
fast path (ASG worker pool): cordon + drain + replace node (#MANUAL)
only if node is critical and irreplaceable: manual cleanup /var/lib/containerd + /var/log (#MANUAL)
```

---

## Decision Trace — Branch C: ASG Node Join Failure

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Check ASG activity | AWS console → Activity tab | Instances terminating immediately after launch | Launch Template/AMI config issue or capacity shortage | 0.85 |
| 2 | Instance boots but not in cluster | `kubectl get nodes` vs EC2 running instances | Instance exists in EC2 but not in node list | user-data/cloud-init or kubelet join failed | 0.85 |
| 3 | Check cloud-init on instance | SSH → `cat /var/log/cloud-init-output.log` | Join command failed or config endpoint wrong | kubeadm join error; LT misconfiguration | 0.90 |
| 4 | Check kubelet logs | `journalctl -u kubelet` | Connection refused to API server | Control plane unreachable or cert mismatch | 0.85 |

**Branch C fix path:**
```
if recent LT/AMI change preceded failure:
  → roll back Launch Template to last known-good version (#MANUAL)
if join config wrong:
  → fix user-data (base64 encoding, endpoint URL, token) then recycle ASG (#MANUAL)
```

---

## Evidence Chain

```
cluster_2_root_questions:
  1. Can the scheduler find a node that matches requests + placement constraints?
  2. Is the node healthy enough to accept workloads (disk, memory, notReady)?
  3. Can new nodes be added if needed (ASG, LT, join)?

key_principle:
  "requests vs allocatable" is the most common mismatch.
  Allocatable = instance_capacity - kubelet/system_reserved — always smaller than spec.
  Placement constraints (nodeSelector + taints + affinity) are silent filters
  that make the eligible node pool narrower than operators expect.
```

---

## Triage Policy (Extracted)

```yaml
policy_name: scheduling-node-pressure-triage

trigger:
  signals:
    - pod_pending
    - pod_evicted
    - node_not_joining
    - job_stuck_pending

branch_selector:
  - IF pod_status == Pending → branch_A
  - IF pod_status == Evicted AND DiskPressure → branch_B
  - IF asg_instance_not_in_cluster → branch_C
  - IF batch_job_stuck → branch_D (terminate job_id via platform API)

branch_A:
  step_1: kubectl describe pod → read scheduler events
  step_2: identify nodeSelector + tolerations in pod spec
  step_3: compare pod requests vs node allocatable
  step_4: check ASG current/max size
  human_gate: all fixes (resize nodegroup, fix affinity, raise ASG max)

branch_B:
  step_1: kubectl describe pod → confirm Evicted + DiskPressure
  step_2: kubectl describe node → confirm ImageGCFailed / EvictionThresholdMet
  step_3: assess whether node can self-heal
  decision: if GC failing repeatedly → replace node (preferred over cleanup)
  human_gate: cordon + drain + node replacement

branch_C:
  step_1: check ASG activity history
  step_2: distinguish launch failure vs join failure
  step_3: for join failure → check cloud-init + kubelet logs on instance
  fast_mitigation: roll back Launch Template to last known-good version
  human_gate: LT modification + ASG recycle

verification:
  branch_A: pod transitions from Pending to Running; node allocatable confirmed sufficient
  branch_B: DiskPressure=False on stable node; no new Evicted pods for 15+ min
  branch_C: node appears in kubectl get nodes; status = Ready

human_gates:
  - any ASG/Launch Template modification
  - node cordon + drain
  - pod resource request changes
  - nodegroup creation or resize
```

---

## Verifier Checklist

- [ ] Pod status is no longer Pending/Evicted
- [ ] Scheduler events are clean (no FailedScheduling)
- [ ] Node condition: DiskPressure=False (branch B)
- [ ] ASG healthy instances > 0, nodes appear in kubectl get nodes (branch C)
- [ ] Workloads stable for >= 15 min with no re-trigger
- [ ] Every #MANUAL action logged

---

## Pattern Cross-Reference

```
cluster_rule:
  "In Cluster 2, always ask three questions in order:
   1. What is the placement constraint (nodeSelector/affinity/taint)?
   2. Does the eligible node have enough allocatable capacity?
   3. Is the node itself healthy (disk, memory, join state)?
   Never resize resources or replace nodes before answering all three."
```
