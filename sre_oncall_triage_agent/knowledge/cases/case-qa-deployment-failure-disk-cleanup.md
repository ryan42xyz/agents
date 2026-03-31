---
metadata:
  kind: case
  status: final
  summary: "Fast triage for QA/Dev deployment failures (suspected disk cleanup/reclaim): confirm the cleanup/reclaim window; use events/logs to find the first broken dependency (often storage/DB); restore the DB first, then rebuild upper-layer services (e.g., BI/analytics UI), and verify readiness."
  tags: ["deployment", "qa", "disk", "db"]
  first_action: "Check disk cleanup/reclaim activity and cluster events first"
  related:
    - ./case-qa-deployment-failure-disk-cleanup.incident.md
    - ./card-k8s-resource-pressure-fast-mitigation.md
    - ./card-yugabyte-debug-ports-commands.md
    - ./card-yugabyte-incident-first-hour.md
    - ./card-yugabyte-metrics-fast-checks.md
    - ./runbook-yugabyte-connection-bootstrapping.md
---

# QA/Dev Deployment Failure (Disk Cleanup) - Troubleshooting Notes

## TL;DR (Do This First)
1. Confirm whether disk cleanup/reclaim happened around the failure window.
2. Use events + logs to find the first broken dependency (often storage/DB).
3. Restore DB dependencies first, then rebuild upper-layer services (e.g., BI/analytics UI) (`#MANUAL`).

## Safety Boundaries
- Read-only: `get/describe/logs`.
- `#MANUAL`: rebuild/redeploy components; modify cleanup jobs/cronjobs.



## Related
- [case-qa-deployment-failure-disk-cleanup.incident.md](./case-qa-deployment-failure-disk-cleanup.incident.md)
- [card-k8s-resource-pressure-fast-mitigation.md](./card-k8s-resource-pressure-fast-mitigation.md)
- [card-yugabyte-debug-ports-commands.md](./card-yugabyte-debug-ports-commands.md)
- [card-yugabyte-incident-first-hour.md](./card-yugabyte-incident-first-hour.md)
- [card-yugabyte-metrics-fast-checks.md](./card-yugabyte-metrics-fast-checks.md)
- [runbook-yugabyte-connection-bootstrapping.md](./runbook-yugabyte-connection-bootstrapping.md)

## Triage

When a QA/Dev deployment fails after disk cleanup/reclaim, a common cause is the cleanup/reclaim loop deleting "expired" disks or reclaiming underlying storage. The key is to prove the cleanup timing and fix in dependency order.

### Symptoms

- Deployment fails: pods do not come up, dependencies unavailable, repeated `CrashLoopBackOff`.
- There are recent signs of disk cleanup/reclaim activity in the environment.

### Minimal Checks (In Order)

Start from disk/cleanup signals, then converge on the first failing component.

```bash
# On the node (if you can access it)
df -h

# In the cluster (example: check cleanup/reclaim jobs/cronjobs)
kubectl get cronjob -A
kubectl get job -A | head

# Events/logs for failing components
kubectl get pods -A | grep -iE 'db|analytics|error|crash'
kubectl describe pod <pod> -n <ns>
kubectl logs <pod> -n <ns> --tail=200
```

### Decision Rules

- Fix in dependency order: storage/DB first, then upper-layer services.
- Rebuild/redeploy is `#MANUAL`: do it in QA/Dev first; record blast radius and rollback path.

## Verification
- DB dependencies recover: connectivity/health checks pass.
- Deployment recovers: `Ready` replicas rise, crash loops stop, error rate drops.

## Closeout
- Record root cause (cleanup timing, reclaimed disks, dependency chain) and the exact remediation steps.
- If the cleanup job/cronjob is the culprit, file follow-ups to adjust retention/guardrails to prevent recurrence.

## One-line Essence

When a QA/Dev deployment fails after disk cleanup/reclaim, prove the cleanup window first, then restore the lowest-layer dependencies (usually DB/storage) before rebuilding upper-layer services.
