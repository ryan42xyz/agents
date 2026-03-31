---
metadata:
  kind: checklist
  status: draft
  summary: "Cluster oncall troubleshooting outline: covers multi-cluster traffic anomalies, cluster health (pod and node distribution), and AWS-layer failure points (master/worker/ASG/AMI). Useful as a quick triage path and layered framework."
  tags: ["k8s", "cluster", "aws", "troubleshooting"]
  first_action: "Snapshot nodes/pods/events; compare multi-cluster traffic"
---

# Cluster Troubleshooting Checklist

## TL;DR (Do This First)
1. Confirm whether this is a single-cluster issue or a multi-cluster issue (start with traffic/latency/error-rate distribution)
2. Take a cluster health snapshot: nodes/pods/events (first falsify a "cluster-wide outage")
3. If node anomalies are concentrated, then drill down into AWS/ASG/instance status (scaling/replacement are write actions)

## Checklist
### 1) Traffic / Multi-Cluster
- Check whether QPS/latency/error rate rises only in one cluster
- If there is a traffic switch mechanism, confirm the switch timestamp aligns with metric changes

### 2) Cluster Health Snapshot (read-only)
```bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp | tail -n 50
```

### 3) Pod / Node Placement
- Check whether unhealthy pods concentrate on certain nodes (same AZ, same ASG, same instance type)
- If it is a node issue, follow the node troubleshooting runbook first (NotReady, DiskPressure, resource exhaustion)

### 4) AWS Layer (write actions require human)
- Look at instance status and ASG activity history first, then decide whether node replacement or LT/AMI rollback is needed

## Stop / Escalate When
- Write actions are required (cordon/drain/scale/rollout restart/ASG update)
- Blast radius is unclear, or there is data risk (DB/storage related)

## Exit Criteria
- You can answer: which layer is failing (traffic/routing vs cluster scheduling vs node health vs AWS infra)
- You have captured evidence (commands output, events, timestamps) and routed to the right owner
- If mitigation requires write actions, it is explicitly handed off as `#MANUAL`
