# Compute Pods

## Purpose

Inspect pod-level compute resources and health.

## Scope

- Pod resource usage (CPU, memory, disk)
- Pod status and restart counts
- Container-level metrics
- Node-level constraints

## Inspection Checklist

1. Pod resources dashboard
   - CPU utilization trends
   - Memory pressure indicators
   - Disk I/O patterns
   - Container-level breakdown

2. Pod status inspection
   - Running vs pending vs failed
   - Restart counts and timestamps
   - Resource limits vs requests

3. Node-level context
   - Node capacity and utilization
   - Pod scheduling constraints
   - Resource contention

## Principles

- Resource metrics are symptoms
- Check pod restarts and evictions
- Consider resource limits, not just usage
- Do NOT assume pods are the root cause
