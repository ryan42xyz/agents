---
metadata:
  kind: runbook
  status: final
  summary: "Kubernetes Node NotReady oncall runbook: symptoms, core commands, common causes (kubelet, resources, networking, AWS), remediation steps, and a prevention checklist."
  tags: ["k8s", "node", "notready", "kubelet"]
  first_action: "Run `kubectl get nodes` and `kubectl describe node`"
---

# Issue Type: Node NotReady

## TL;DR (Do This First)
1. Identify affected nodes: `${CLUSTER_ALIAS} get nodes | grep -i NotReady`
2. Snapshot node state: `${CLUSTER_ALIAS} describe node <node-name>` (focus on Conditions + Events)
3. Check impact: `${CLUSTER_ALIAS} get pods -A -o wide | grep <node-name>`
4. If remediation requires cordon/drain/reboot/ASG replace, stop and hand off as `#MANUAL`

## Safety Boundaries
- Read-only: `get/describe/logs/top` and log inspection
- `#MANUAL`: cordon/drain, kubelet restarts, instance replacement, ASG changes

## Verification
- Node returns to `Ready`
- Pods recover (no mass `Terminating`/`ContainerCreating` stuck)
- Alerts clear (`KubeNodeNotReady`/`KubeletDown`)

## Problem Pattern
- Category: Node Issues
- Symptoms: Node status "NotReady", pods stuck in "Terminating", kubelet not reporting status
- Alert Pattern: "KubeNodeNotReady", "KubeletDown" alerts

## Standard Investigation Process

## Triage

- Triage via node Events and Conditions: check Conditions + Events first, then correlate with kubelet/resources/network/AWS.

### 1. Initial Assessment
```bash
# Check node status
${CLUSTER_ALIAS} get nodes | grep NotReady
${CLUSTER_ALIAS} describe node <node-name>

# Check pods on the node
${CLUSTER_ALIAS} get pods --all-namespaces -o wide | grep <node-name>
```

### 2. Common Causes

#### Kubelet Service Issues
- Check kubelet status: `systemctl status kubelet`
- Check logs: `journalctl -u kubelet --since "1 hour ago"`

#### System Resource Exhaustion
- Check resources: `df -h`, `free -m`, `top -n 1`
- Check OOM events: `dmesg | grep -i "out of memory"`

#### Network Connectivity Issues
- Check network plugin: `${CLUSTER_ALIAS} get pods -n kube-system | grep calico`
- Test connectivity: `ping -c 3 <api-server-ip>`

#### AWS Instance Issues
- Check status: `aws ec2 describe-instance-status --instance-id <instance-id>`

### 3. Resolution Steps

#### For Kubelet Issues
- Restart kubelet: `systemctl restart kubelet`
- Check configs: `cat /var/lib/kubelet/config.yaml`

#### For Resource Exhaustion
- Clean disk: `journalctl --vacuum-time=1d`
- Check heavy processes: `ps aux --sort=-%mem | head`

#### For AWS Instance Issues
- Reboot: `aws ec2 reboot-instances --instance-ids <instance-id>`

#### For Stuck Pods
- Force delete: `${CLUSTER_ALIAS} delete pod <pod-name> -n <namespace> --force --grace-period=0`

### 4. Prevention
- Implement resource limits and requests
- Set up node health monitoring
- Use pod disruption budgets
- Consider dedicated node pools for resource-intensive workloads

## Example Case
- Reference: CLUSTER_EASTPRODA_20250505
- Issue: Node ip-172-30-66-69.ec2.internal NotReady, pods stuck in Terminating
- Cause: High resource utilization (98% CPU, 93% memory) likely contributed
- Resolution: Checked AWS health, force-deleted stuck pods, rebooted instance
- Prevention: Implemented resource allocation review
