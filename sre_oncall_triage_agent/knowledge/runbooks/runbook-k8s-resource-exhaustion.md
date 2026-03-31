---
metadata:
  kind: runbook
  status: final
  summary: "Kubernetes oncall resource exhaustion guide: identify DiskPressure, no space left on device, CPU/memory pressure, and similar signals; provides practical steps like cleaning Docker/logs/images, `crictl rmi --prune`, and node cordon/drain, plus notes on service impact and safety considerations."
  tags: ["k8s", "diskpressure", "cpu", "memory"]
  first_action: "Describe node to identify the pressure signal"
---

# Kubernetes Resource Exhaustion Handling Guide

## TL;DR (Do This First)
1. Confirm the pressure signal: `kubectl describe node <node>` (DiskPressure/MemoryPressure)
2. Identify the biggest consumers (node + pods), and whether it's ephemeral-storage vs rootfs vs inode
3. Prefer the least risky mitigation first (free space / move workload / replace node) before deleting data
4. Any cleanup/restart/drain is `#MANUAL`

## Safety Boundaries
- Read-only: `get/describe/top/logs`
- `#MANUAL`: `docker system prune`, deleting logs/data, cordon/drain, node replacement

## Triage

- Start with `kubectl describe node <node>` to identify DiskPressure/MemoryPressure/CPU saturation, and whether the bottleneck is nodefs/imagefs/inode.

## Verify

- Pressure signals recover (DiskPressure/MemoryPressure=False), alerts clear, and core workloads return to stable operation.

During Kubernetes oncall, resource exhaustion is a common issue. This document provides guidance for handling different resource constraint problems, including (but not limited to) disk space exhaustion and CPU/memory pressure.

## 1. AWS disk space exhaustion

### 1.1 Identification

Common symptoms of disk space exhaustion:

- Pod scheduling fails and errors include `no space left on device`
- Node condition shows `DiskPressure: True`
- Service suddenly becomes unavailable or responds slowly
- Log writes fail

How to check:

```bash
# Check node status
kubectl get nodes
kubectl describe node <node-name>

# Check disk usage on the node
df -h

# Get disk info for the AWS EC2 instance
aws ec2 describe-instances --instance-ids <instance-id> --query "Reservations[*].Instances[*].[InstanceId, BlockDeviceMappings[*].Ebs.VolumeId, BlockDeviceMappings[*].Ebs.VolumeSize]" --output table
```

### 1.2 Cleanup options

1. **Clean Docker resources**:

```bash
# Prune unused Docker images/containers/networks
docker system prune -f

# Deeper cleanup, including unused volumes
docker system prune -a --volumes -f
```

2. **Clean log files**:

```bash
# Find large log files
find /var/log -type f -name "*.log" -size +100M

# Clean up or compress logs
journalctl --vacuum-time=1d  # keep only the last 1 day of journald logs
```

3. **Clean kubelet and container runtime artifacts**:

```bash
# Remove unused images (prune)
crictl rmi --prune
```

4. **Clean temporary files**:

```bash
# Clean /tmp
find /tmp -type f -atime +10 -delete
```

### 1.3 Node drain

If cleanup does not resolve the issue, you may need to drain the node to reallocate workloads:

```bash
#MANUAL
# Mark node unschedulable
kubectl cordon <node-name>

# Evict Pods to other nodes
kubectl drain <node-name> --ignore-daemonsets --delete-local-data
```

**Potential impact**:
- Services may have brief interruptions, especially if replicas are insufficient
- If the cluster is resource constrained, Pods may fail to reschedule onto other nodes
- StatefulSet Pods are recreated but keep the same PVC
- Local storage data may be lost (if using `--delete-local-data`)

**Best practices**:
- Drain during off-peak hours
- Ensure critical services have enough replicas
- Use PodDisruptionBudget to limit concurrent disruptions for critical services
- Test on a single non-critical node first

### 1.4 Disk expansion

If cleanup is not sufficient, expand the AWS EBS volume:

```bash
# Get volume ID
aws ec2 describe-instances --instance-ids <instance-id> --query "Reservations[*].Instances[*].BlockDeviceMappings[*].Ebs.VolumeId" --output text

# Modify volume size
aws ec2 modify-volume --volume-id <volume-id> --size <new-size-in-gb>

# Expand filesystem (run on the instance)
resize2fs /dev/<device-name>  # for ext4
xfs_growfs /mountpoint  # for XFS
```

**Notes**:
- Increasing volume size does not require stopping the instance, but you may need to restart specific services
- AWS EBS volumes can only be increased, not decreased
- After expansion, extend the filesystem to use the added space

## 2. Node CPU/memory pressure

### 2.1 Identification

```bash
# Check node resource usage
kubectl top nodes
kubectl describe node <node-name>

# Check Pods with high CPU/memory usage
kubectl top pods --all-namespaces
```

### 2.2 Remediation

1. **Adjust Pod resource requests/limits**:

```bash
#MANUAL
# Edit deployment to adjust resource requests/limits
kubectl edit deployment <deployment-name>
```

Update `resources.requests` and `resources.limits` for CPU and memory.

2. **Scale out Pods horizontally**:

```bash
#MANUAL
kubectl scale deployment <deployment-name> --replicas=<number>
```

3. **Evict low-priority Pods**:

```bash
#MANUAL
# Manually delete a non-critical Pod
kubectl delete pod <pod-name>
```

4. **Node-level actions**:
   - Drain as described above
   - Consider adding new nodes to the cluster

## 3. PersistentVolume capacity issues

### 3.1 Identification

```bash
# Check PVC status
kubectl get pvc --all-namespaces
kubectl describe pvc <pvc-name>
```

### 3.2 Remediation

1. **Expand an existing PVC** (if the StorageClass supports volume expansion):

```bash
#MANUAL
kubectl edit pvc <pvc-name>
# Modify spec.resources.requests.storage
```

2. **Create a new, larger PVC and migrate data**:
   - Create the new PVC
   - Deploy a temporary Pod mounting both PVCs
   - Copy data from the old volume to the new one
   - Update the application to use the new PVC

### 3.3 Expand using AWS EBS

For PVCs backed by AWS EBS, you can:

```bash
#MANUAL
# Get the EBS volume ID for the PV
kubectl describe pv <pv-name>

# Expand via AWS CLI
aws ec2 modify-volume --volume-id <volume-id> --size <new-size-in-gb>

# Update the PVC object to request the new size
kubectl patch pvc <pvc-name> -p '{"spec":{"resources":{"requests":{"storage":"<new-size>Gi"}}}}'
```

## 4. Other resource constraints

### 4.1 Network constraints

Symptoms and mitigations:
- **Node NIC hits bandwidth limits**
  - Monitor network traffic and identify high-traffic Pods
  - Consider higher-bandwidth instance types
  - Implement traffic limiting policies

- **Connection count hits limits**
  - Increase node `fs.file-max` and `net.ipv4.ip_local_port_range`
  - Ensure applications close connections properly
  - Consider connection pooling

### 4.2 API Server constraints

Symptoms and mitigations:
- **Too many API Server requests**
  - Reduce client request frequency
  - Increase API Server resources
  - Implement flow control and rate limiting

- **etcd performance issues**
  - Monitor etcd metrics
  - Clean up unnecessary objects
  - Consider SSD storage and higher-performance instances

## 5. Prevention

### 5.1 Proactive monitoring

Alert on these metrics:
- Node disk usage (warning: >75%, critical: >85%)
- Node CPU and memory utilization
- Pod usage-to-limit ratio
- PVC usage

### 5.2 Resource quotas

Set resource quotas per namespace:

```bash
kubectl create quota <quota-name> --namespace=<namespace> \
  --hard=requests.cpu=<cpu-limit>,requests.memory=<memory-limit>,limits.cpu=<cpu-limit>,limits.memory=<memory-limit>
```

### 5.3 Cluster autoscaling

Configure Kubernetes Cluster Autoscaler to adjust cluster size automatically based on resource demand.

### 5.4 Routine cleanup

Set up routine cleanup tasks:
- Delete completed Jobs and related Pods
- Remove unused Docker images
- Archive old log files

## 6. References

- [Kubernetes docs: resource pressure](https://kubernetes.io/docs/tasks/administer-cluster/out-of-resource/)
- [AWS EBS volume modification guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/requesting-ebs-volume-modifications.html)
- [Kubernetes best practices: resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
