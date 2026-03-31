---
metadata:
  kind: case
  status: final
  summary: "Troubleshoot AWS ASG scale-out instances failing to boot or join Kubernetes: isolate layer-by-layer across ASG/Launch Template, user-data/cloud-init, kubeadm join, and kubelet logs; prefer rolling back to a known-good LT/AMI to restore capacity fast."
  tags: ["aws", "asg", "ec2", "k8s", "node"]
  first_action: "Check ASG Activity and instance lifecycle first"
  related:
    - ./case-aws-asg-scale-out-node-join-failure.incident.md
    - ./card-k8s-node-notready-fast-triage.md
    - ./card-kubectl-describe-node-key-signals.md
    - ./runbook-k8s-upgrade-plan-runbook.md
    - ./runbook-aws-iam-access-denied-troubleshooting.md
    - ./runbook-jenkins-s3-permission-troubleshooting.md
---

# AWS ASG Scale-Out / Node Join Failure

## TL;DR (Do This First)
1. Check ASG Activity + instance lifecycle (is it terminated immediately?)
2. Instance boots but the node does not join: check user-data/cloud-init results + kubelet logs
3. Prefer rolling back to a known-good Launch Template/AMI to restore capacity first (`#MANUAL`)

## Safety Boundaries
- Read-only: view ASG/EC2 state, read logs
- `#MANUAL`: modify ASG/LT, run kubeadm reset/join, replace nodes



## Related
- [case-aws-asg-scale-out-node-join-failure.incident.md](./case-aws-asg-scale-out-node-join-failure.incident.md)
- [card-k8s-node-notready-fast-triage.md](./card-k8s-node-notready-fast-triage.md)
- [card-kubectl-describe-node-key-signals.md](./card-kubectl-describe-node-key-signals.md)

## Triage
- First decide which stage fails: instance launch vs cluster join; the paths are completely different
- Launch failure: check ASG Activity history, EC2 instance status checks, termination reason
- Join failure: check whether user-data/cloud-init ran successfully, and `journalctl -u kubelet` on the instance
- If capacity is impacted: roll back to a known-good Launch Template/AMI first (`#MANUAL`)

## Trigger / Symptoms

- ASG scale-out instances fail to come up (instance never becomes healthy / terminated immediately)
- Instance boots but cannot join the cluster (node never appears / stays NotReady)

## Instance cannot launch (launch failure)

Example: roll back to a known-good Launch Template / AMI:

```sh
#MANUAL
# Example (fill in your ASG name, LT id/version, and region)
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name <asg-name> \
  --launch-template "LaunchTemplateId=<lt-id>,Version=<lt-version>" \
  --region <region>
```

## Isolation / Troubleshooting Steps

Stop the bleeding first
- Restore schedulable capacity first:
  - Roll back to a known-good Launch Template/AMI
  - Or switch to another known-good ASG/node group (if available)

Then pinpoint the failing stage
1. Does the instance boot and remain healthy?
  - Usually an AWS/ASG/LT/AMI config issue or capacity shortage
2. Does the instance boot but fail to join the cluster?
  - Check user-data/cloud-init (join command, control-plane endpoint, kubelet config)
  - After SSH to the instance:
    - Confirm kubelet is running
    - Inspect/re-validate the join command and its logs

Common pitfalls
- user-data encoding: confirm whether the Launch Template expects plaintext or "base64 encoded", and ensure it matches what you provide.

On-instance checks (instance boots but the node does not join):

```sh
# Read-only (on the instance)
sudo cloud-init status --long || true
sudo journalctl -u kubelet --no-pager -n 200
sudo systemctl status kubelet --no-pager
```

If you must re-join (large blast radius):

```sh
#MANUAL
sudo kubeadm reset -f
sudo kubeadm join <control-plane-endpoint>:6443 \
  --token <kubeadm-bootstrap-token> \
  --discovery-token-ca-cert-hash <discovery-token-ca-cert-hash>
```

## Decision / Action Boundaries

- Prefer restoring capacity by rolling back/switching to a known-good ASG or LT version first, then isolate root cause.
- Treat all write operations (ASG updates, kubeadm reset/join) as manual; relevant command blocks are marked `#MANUAL`.

## Verification

- EC2 instances stay Running (no repeated termination)
- On the node: `systemctl status kubelet` is healthy; `journalctl -u kubelet` has no repeating fatal errors
- In the cluster: `kubectl get nodes` shows the new node and it becomes Ready

## Closeout

- ASG scale-out reliably brings up instances (no immediate termination)
- New nodes join the cluster and stay Ready
- Workloads resume normal scheduling and symptoms stop


## One-line Essence
- Roll back to a known-good LT/AMI to restore capacity fast, then decide whether the issue is in instance launch or kubelet/kubeadm join.
