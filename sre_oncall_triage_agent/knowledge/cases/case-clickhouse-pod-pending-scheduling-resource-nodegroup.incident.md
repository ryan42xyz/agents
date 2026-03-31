---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-clickhouse-pod-pending-scheduling-resource-nodegroup.md
  title: "ClickHouse Pod Pending After Resource Increase (NodeGroup Mismatch)"
  summary: "EN: ClickHouse StatefulSet pod stayed Pending after raising CPU/memory requests; scheduler reported Insufficient cpu/memory and node affinity/selector mismatch. Root cause was requests exceeding allocatable of the dedicated ClickHouse node group (r7i.2xlarge) while larger nodes existed but lacked the required dedicated label; mitigation was introducing a larger dedicated node group (r7i.4xlarge) preserving node labels/taints so the pod could schedule."
  tags: [clickhouse, kubernetes, scheduling, pending, resources, nodegroup, node-selector, affinity, aws, asg]
  patterns: [k8s-scheduling-requests-exceed-allocatable, label-pinned-workload-nodegroup-mismatch]
---

# Incident: ClickHouse Pod Pending After Resource Increase (NodeGroup Mismatch)

## 1. Incident Overview
- Date: <YYYY-MM-DD> (local time <TZ>)
- Severity: <SEV-2|SEV-3> (impact limited to <env>)
- Duration: <~minutes> (from resource change to pod scheduled)
- System: ClickHouse (StatefulSet/operator-managed) in `preprod`
- Impact: one ClickHouse instance unavailable because a critical pod could not schedule

## 2. System Context
- Workload isolation strategy: ClickHouse workloads pinned to dedicated nodes via label
- Scheduler constraints: `nodeSelector` and possibly taints/tolerations

## 3. Environment
- Cloud: AWS
- Platform: Kubernetes
- Dedicated ClickHouse node group:
  - Instance type: `r7i.2xlarge` (8 vCPU / 64GB)
  - Label: `dedicated-node=true`
- Other node group:
  - Instance type: `r7i.4xlarge` (16 vCPU / 128GB)
  - Missing `dedicated-node=true` label

## 4. Incident Trigger
- Trigger: Oncall request increased ClickHouse pod resources due to higher workload demand
- Change:
  - CPU: `2` -> `8`
  - Memory: `18Gi` -> `64Gi`
- Result: pod `chi-dv-datavisor-0-0-0` stayed `Pending`

## 5. Impact Analysis
- Blast radius: `preprod` ClickHouse instance
- User-visible symptom: ClickHouse unavailable / queries fail
- Data loss: none observed (scheduling failure prevented start; no evidence of data corruption)
- SLO/SLA breach: not applicable (preprod)

## 6. Constraints
- Read-only: `kubectl get/describe`, view node allocatable/labels
- `#MANUAL`: ASG/node group changes, label/taint changes, StatefulSet resource changes

## 7. Investigation Timeline
- Observed pod stuck `Pending`
- `kubectl describe pod` events indicated:
  - `Insufficient cpu`
  - `Insufficient memory`
  - `node(s) didn't match Pod's node affinity/selector`
- Confirmed ClickHouse pod required:

```yaml
nodeSelector:
  dedicated-node: "true"
```

- Checked dedicated node group allocatable resources (after overhead):
  - CPU ~= 7.5
  - Memory ~= 60Gi
- Compared against new pod requests:
  - CPU: 8
  - Memory: 64Gi
- Determined request > allocatable, so no dedicated node could satisfy the pod
- Verified larger nodes existed but were not eligible due to missing label

Timeline (sanitized):
- T0: resource bump applied (CPU/mem increased).
- T0+<m>: pod observed `Pending`; `FailedScheduling` events collected.
- T0+<m>: feasibility confirmed (`requests > allocatable`) for dedicated pool.
- T0+<m>: mitigation chosen: add larger dedicated pool preserving `dedicated-node=true`.
- T0+<m>: new node joined; pod scheduled and became Ready.

## 8. Root Cause
- Primary root cause: Pod resource requests exceeded allocatable capacity of the dedicated ClickHouse node group.
- Contributing cause: Strict scheduling constraint (`nodeSelector dedicated-node=true`) prevented scheduling onto larger general-purpose nodes.

## 9. Resolution
- Introduced a new dedicated node group with larger instance type:
  - `r7i.4xlarge`
- Preserved bootstrap configuration to keep node labels:
  - `--node-labels=dedicated-node=true`
- Ensured taints/tolerations remained compatible
- Scaled the new ASG to provision a node
- Scheduler successfully placed the ClickHouse pod onto the new node

Change log (required for production rigor):
- `#MANUAL` <time> <owner>: created/updated node group `<new-nodegroup>` (instance type `<type>`, max `<n>`).
- `#MANUAL` <time> <owner>: ensured label/taint compatibility (`dedicated-node=true`, tolerations preserved).
- Rollback plan: scale `<new-nodegroup>` to 0 after reverting requests or migrating workload; remove labels if they were broadened.

## 10. Prevention / Improvement
1. Align pod requests with node group allocatable capacity (budget headroom; do not size to raw instance spec).
2. Treat resource bumps as a coupled change: update node groups (instance type / autoscaler limits) together.
3. Maintain clear workload isolation using labels/taints/node groups; ensure larger capacity pools carry required labels when needed.
4. Add a pre-change check: for pinned workloads, validate `requests <= allocatable` for candidate nodes.

## 11. Generalizable Lessons
- Scheduler failures are often a combination of "not enough resources" + "not enough eligible nodes".
- `allocatable` is the real constraint; instance spec is only a hint.
- A strict `nodeSelector` is a hard gate; it overrides "there are bigger nodes" arguments.

## Tags & Patterns
- Tags: clickhouse, kubernetes, scheduling, pending, resources, nodegroup, node-selector, affinity, aws, asg
- Patterns: k8s-scheduling-requests-exceed-allocatable, label-pinned-workload-nodegroup-mismatch
- First Action: describe the pending pod and record scheduler events

## Evidence Mapping
- Symptom evidence -> "Pod stayed Pending; events show Insufficient cpu/memory" (case-clickhouse-pod-pending-scheduling-resource-nodegroup.md:Symptom)
- Constraint evidence -> "nodeSelector pins workload to dedicated-node=true" (case-clickhouse-pod-pending-scheduling-resource-nodegroup.md:Investigation (Standard Path))
- Resource feasibility rule -> "Compare pod requests vs node allocatable" (case-clickhouse-pod-pending-scheduling-resource-nodegroup.md:Investigation (Standard Path))
- Fix path -> "Scale dedicated node group or lower requests" (case-clickhouse-pod-pending-scheduling-resource-nodegroup.md:Resolution Options)

## Evidence Snippets (Sanitized)

FailedScheduling excerpt:

```text
Warning  FailedScheduling  <time>  default-scheduler  0/<N> nodes are available: Insufficient cpu; Insufficient memory; node(s) didn't match Pod's node affinity/selector
```

Feasibility comparison:

```text
pod requests: cpu=8, memory=64Gi
dedicated pool allocatable (typical): cpu≈7.5, memory≈60Gi
conclusion: requests exceed allocatable => cannot schedule
```
