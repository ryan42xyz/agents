---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-aws-asg-scale-out-node-join-failure.md
  title: "AWS ASG Scale-Out / Node Join Failure"
  summary: "ASG scale-out failed to provide usable Kubernetes worker capacity: instances terminated early or stayed NotReady; triage splits into AWS provisioning and kubeadm join paths; the fastest mitigation is rolling back to a last known-good Launch Template/AMI; includes safety boundaries and verification checks."
  tags: [aws, asg, ec2, kubernetes, kubeadm, kubelet, userdata, capacity]
  patterns: [asg-scaleout-node-join-failure]
---

# Incident: AWS ASG Scale-Out / Node Join Failure

## 1. Incident Overview
- Date: TBD
- Severity: TBD
- Duration: TBD
- System: AWS Auto Scaling Group providing Kubernetes worker capacity
- Impact: Capacity shortfall and/or new nodes cannot become `Ready`, causing scheduling pressure (quantification: TBD)

## 2. System Context
- Architecture (relevant): ASG -> EC2 boot -> user-data/cloud-init -> kubelet -> `kubeadm join` -> node registers
- Scale: TBD

## 3. Environment
- Cloud: AWS
- Compute: EC2 via ASG
- Kubernetes provisioning: `kubeadm` (seen in runbook commands)
- Launch Template / AMI version: TBD (case emphasizes rollback)
- Region/cluster identifiers: sanitized/TBD

## 4. Trigger
- Trigger: ASG scale-out did not yield usable worker capacity (alert details: TBD)

## 5. Impact Analysis
- Blast radius: cluster capacity; any workloads requiring new nodes
- User-visible symptoms: TBD (likely pending pods/scheduling failures)
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: describe ASG/EC2 status, read logs
- `#MANUAL`: ASG/LT updates, `kubeadm reset/join`, node replacement

## 7. Investigation Timeline
- Phase 1: Is AWS provisioning failing, or is cluster join failing?
  - Check ASG activity + instance lifecycle (terminating immediately vs stable Running)
 - Phase 2: If the instance is Running but the node does not join
  - inspect user-data execution
  - check `systemctl status kubelet` and `journalctl -u kubelet`
  - validate `kubeadm join` parameters/token/hashes (details in case are placeholders)
 - Phase 3: Common pitfalls
  - user-data base64 setting mismatch can break bootstrapping

## 8. Root Cause
- Root cause: TBD (this case is primarily a structured triage/runbook; it captures symptom classes and common pitfalls, and may not have a single confirmed root cause).
- Symptom vs root cause:
  - Symptom: instances terminate immediately OR node never becomes Ready
  - Root cause candidates: ASG/LT/AMI misconfig, user-data execution failure, kubelet start failure, `kubeadm join` failure

## 9. Mitigation
- Stop the bleeding immediately: roll back to a last known-good Launch Template/AMI, or switch to a previously working ASG to restore schedulable capacity (`#MANUAL`).
- Verification:
  - EC2 instances stay Running
  - kubelet is healthy on the node
  - `kubectl get nodes` shows new nodes Ready

## 10. Prevention / Improvement
- Version and validate provisioning artifacts (LT/AMI/user-data) with quick rollback.
- Add automated join SLO: "instance Running -> node Ready within N minutes".
- Add explicit checks for user-data encoding/base64 expectations in the pipeline.
- Maintain a break-glass join-debug runbook (kubelet logs + join step).

## 11. Generalizable Lessons
- Split early: "instance provisioning" vs "k8s join".
- Restore capacity first (rollback), then do deep RCA safely.
- Kubelet logs + user-data are usually the highest signal for join failures.
- Pattern Card:
  - Pattern name: asg-scaleout-node-join-failure
  - When it happens: ASG scale-out events
  - Fast detection signals: EC2 lifecycle churn; node missing/NotReady
  - Fast mitigation: rollback LT/AMI; replace node
- Common pitfalls: user-data encoding; expired/incorrect join token

## Tags & Patterns
- Tags: aws, asg, ec2, kubernetes, kubeadm, kubelet, userdata, capacity
- Patterns: asg-scaleout-node-join-failure
- First Action: check ASG activity and whether instances terminate immediately

## Evidence Mapping
- Symptom class -> "Scale-out instances fail to come up (not launched or terminate immediately)" (case-aws-asg-scale-out-node-join-failure.md:Trigger/Symptom)
- Symptom class -> "Instances boot but cannot join the Kubernetes cluster (node missing or NotReady)" (case-aws-asg-scale-out-node-join-failure.md:Trigger/Symptom)
- First checks -> "Check ASG activity + instance lifecycle (is it terminating immediately?)" (case-aws-asg-scale-out-node-join-failure.md:TL;DR)
- Join-path focus -> "If instance boots but node not joining: inspect user-data + kubelet logs" (case-aws-asg-scale-out-node-join-failure.md:TL;DR)
- Mitigation preference -> "Prefer rollback to last known-good LT/AMI to restore capacity (`#MANUAL`)" (case-aws-asg-scale-out-node-join-failure.md:TL;DR)
- Phase split -> "Determine which phase is failing: instance launch vs. K8s join" (case-aws-asg-scale-out-node-join-failure.md:Triage)
- Known pitfall -> "Known pitfalls:" (case-aws-asg-scale-out-node-join-failure.md:Known Pitfalls)
- Known pitfall -> "- user-data base64 encoding/config mismatch" (case-aws-asg-scale-out-node-join-failure.md:Known Pitfalls)
- Verification -> "- `kubectl get nodes` shows the new nodes and they are Ready" (case-aws-asg-scale-out-node-join-failure.md:Verify)
