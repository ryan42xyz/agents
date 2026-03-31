---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-qa-deployment-failure-disk-cleanup.md
  title: "QA/Dev Deployment Failure (Disk Cleanup Suspected)"
  summary: "EN: QA/dev deployment failures suspected to be caused by periodic disk cleanup/reclaim; triage focuses on confirming cleanup jobs, collecting events/logs, and restoring DB dependencies before rebuilding upper services."
  tags: [kubernetes, qa, dev, deployment, disk, cleanup, db]
  patterns: [qa-disk-cleanup-cascading-failure]
---

# Incident: QA/Dev Deployment Failure (Disk Cleanup Suspected)

## 1. Incident Overview

- Date: TBD
- Severity: TBD
- Duration: TBD
- System: QA/dev Kubernetes-based deployment stack (dependencies mentioned: DB, upper services)
- Impact: QA/dev pods fail to start / dependencies unavailable / repeated CrashLoop (quantification: TBD)

## 2. System Context

- Dependency order matters: restore DB first, then rebuild upper services.
- Dependency order matters: restore DB first, then rebuild upper services.
- Suspected infra factor: periodic disk cleanup/reclaim job in QA/dev.

Architecture (conceptual):
Client/QA users
  -> app services (upper services)
  -> DB dependencies
  -> storage + cleanup jobs

## 3. Environment

- Environment: QA/dev
- Cloud/platform: TBD
- Kubernetes version: TBD
- Storage/PVC details and cleanup mechanism: TBD

## 4. Incident Trigger

- Trigger: QA/dev deployment failure (exact change/event: TBD)
- Detection signals (from notes): pod startup failures, dependency outages, repeated CrashLoop

## 5. Impact Analysis

- Blast radius: QA/dev (production impact: not indicated)
- Affected components: DB dependency and upper services mentioned; exact set TBD
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints

- Read-only: `get/describe/logs`
- `#MANUAL`: rebuild/redeploy components; disk cleanup job changes
- Access is conditional: node-side checks only if you can log into nodes

## 7. Investigation Timeline

- Timestamps: TBD
- Step 1: confirm disk cleanup/reclaim happened around the window
  - cluster: `kubectl get cronjob -A`, `kubectl get job -A | head`
  - node (if possible): `df -h`
- Step 2: collect first-failure evidence
  - `kubectl describe pod <pod> -n <ns>`
  - `kubectl logs <pod> -n <ns> --tail=200`
- Step 3: restore in dependency order
  - DB health first, then rebuild upper services

## 8. Root Cause

- Root cause: TBD
- Working hypothesis: periodic cleanup job deletes/reclaims "expired" disks in QA/dev, causing cascading failures.

## 9. Resolution

- Resolution applied: TBD (notes provide triage + decision order)
- Mitigation order (recommended): restore DB first; rebuild upper services after DB is healthy (`#MANUAL`)
- Verification:
  - DB connectivity/health checks pass
  - Deployments regain Ready replicas; error rate decreases

## 10. Prevention / Improvement

- Add visibility/alerts around disk cleanup/reclaim jobs and deletions.
- Add guardrails so cleanup cannot delete disks used by active QA/dev clusters.
- Document dependency-order recovery (DB first -> app later).
- Align QA/dev resource/configs with known-good environment; track drift.

## 11. Generalizable Lessons

- Identify the first broken dependency before rebuilding higher layers.
- QA/dev still needs guardrails; cleanup automation can cause non-obvious cascades.
- Treat rebuild/redeploy as `#MANUAL` and verify rollback paths.
- Pattern Card:
  - Pattern name: qa-disk-cleanup-cascading-failure
  - When it happens: periodic cleanup/reclaim jobs run
  - Fast detection signals: cluster events + sudden dependency outages; disk usage anomalies
  - Fast mitigation: stop cleanup (if applicable) + restore DB + rebuild apps
- Common pitfalls: rebuilding apps before DB; missing the cleanup job evidence window

## Tags & Patterns
- Tags: kubernetes, qa, dev, deployment, disk, cleanup, db
- Patterns: qa-disk-cleanup-cascading-failure
- First Action: check whether cleanup/reclaim jobs ran near the failure window

## Evidence Mapping

- Trigger/Symptoms -> "QA/dev deployment failed: pods did not start, dependencies were unavailable, and CrashLoop repeated" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- Hypothesis -> "Periodic cleanup/reclaim jobs may be deleting or reclaiming disks considered 'expired'" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- First action -> "Confirm whether disk cleanup/reclaim happened around the failure window" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- Minimal triage -> "kubectl get cronjob -A" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- Minimal triage -> "kubectl describe pod <pod> -n <ns>" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- Dependency order -> "Recover in dependency order: ensure DB is healthy before rebuilding upper services" (case-qa-deployment-failure-disk-cleanup.md:Triage)
- Safety boundary -> "- Read-only: `get/describe/logs`" (case-qa-deployment-failure-disk-cleanup.md:Safety Boundaries)
- Safety boundary -> "- `#MANUAL`: rebuild/redeploy components, disk cleanup jobs changes" (case-qa-deployment-failure-disk-cleanup.md:Safety Boundaries)
- Verification -> "- Critical dependency (DB) returns healthy; connectivity/health checks pass" (case-qa-deployment-failure-disk-cleanup.md:Verify)
