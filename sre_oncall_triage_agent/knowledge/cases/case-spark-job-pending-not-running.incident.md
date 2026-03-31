---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-spark-job-pending-not-running.md
  title: "Spark Job Stuck Pending / Not Running (Did Not Start Within 90 Minutes)"
  summary: "EN: A Spark job did not start within 90 minutes; triage extracts job_id, confirms stuck Init/Terminating state in Kubernetes, terminates via DCluster API, and verifies no zombie namespaces/pods; optional recovery rebuilds worker pool only when no running jobs exist."
  tags: [spark, kubernetes, scheduler, luigi, dcluster, job-stuck]
  patterns: [spark-job-stuck-terminate-and-cleanup]
---

# Incident: Spark Job Stuck Pending / Not Running (Did Not Start Within 90 Minutes)

## 1. Incident Overview
- Date: TBD
- Severity: TBD
- Duration: TBD
- System: Luigi scheduler submits Spark jobs to a Kubernetes-backed Spark cluster; job lifecycle managed by DCluster API
- Impact: job delayed/not executed; potential cluster resource waste due to zombie namespaces/pods (user impact: TBD)

## 2. System Context
- Architecture (relevant): Luigi -> DCluster API -> Kubernetes job namespace/pods -> Spark master/worker pool
- Mapping rule: namespace can end with `job_id` (used for quick identification)

## 3. Environment
- Platform: Kubernetes
- Access tooling: cluster alias `kwestprodb` (environment-specific)
- Spark cluster style: long-living master + worker pool (StatefulSet)
- Versions: TBD

## 4. Incident Trigger
- Alert:
  - `[Nasa-Luigi] sparkconnectorrunner didnotstartwithin90 minutes`

## 5. Impact Analysis
- Blast radius: primarily the affected job; can extend if stuck jobs accumulate
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: get/describe/logs
- `#MANUAL`: terminate job via DCluster; rebuild worker pool
- Safety constraint: do not rebuild worker pool if there are running jobs

## 7. Investigation Timeline
- Get `job_id` from the alert/mgt record.
- Confirm stuck state in Kubernetes:
  - check pods across namespaces and filter by `job_id`
  - look for `Init:0/1` or long `Terminating` and never reaching Running
- Decision: "won't self-heal"; terminate job to unblock resources (`#MANUAL`).
- Verify:
  - no zombie namespaces/pods remain
  - next run can start
- Optional recovery:
  - if no jobs are running, scale worker pool down to 0 then rebuild to desired replicas (`#MANUAL`).

## 8. Root Cause
- Root cause: TBD
- Most likely class (not proven in notes): Spark master / worker pool abnormality.

## 9. Resolution
- Mitigation: terminate the job via DCluster API (`#MANUAL`).
- Verification: the job pods disappear and cluster returns to healthy scheduling.
- Optional: rebuild worker pool after confirming no running jobs.

## 10. Prevention / Improvement
- Add alerts for stuck job namespaces/pods (Init/Terminating duration thresholds).
- Add worker pool health/capacity dashboards (ready replicas, registration to master).
- Automate safe cleanup of zombie namespaces/pods after termination (guarded).
- Capture structured RCA data during oncall: job_id, namespace, pod states, master/worker signals.

## 11. Generalizable Lessons
- Always start from a single immutable identifier (`job_id`) and map to K8s resources.
- Termination is only half the fix; cleanup verification prevents silent capacity leaks.
- Separate "unblock now" (terminate job) from "platform recovery" (worker pool rebuild).
- Pattern Card:
  - Pattern name: spark-job-stuck-terminate-and-cleanup
  - When it happens: jobs stay Init/Pending/Terminating and never run
  - Fast detection signals: alert did-not-start; `Init:0/1`, long `Terminating`
  - Fast mitigation: terminate via job control API; verify cleanup
- Common pitfalls: rebuilding worker pool while jobs are running; not verifying zombies

## Tags & Patterns
- Tags: spark, kubernetes, scheduler, luigi, dcluster, job-stuck
- Patterns: spark-job-stuck-terminate-and-cleanup
- First Action: extract `job_id` then `kwestprodb get pod -A | grep <job_id>`

## Evidence Mapping
- Alert -> "[Nasa-Luigi] sparkconnectorrunner didnotstartwithin90 minutes" (case-spark-job-pending-not-running.md:Triage)
- Core judgment -> "Spark job was created but never reached Running" (case-spark-job-pending-not-running.md:Triage)
- Non-self-healing -> "The issue did not self-heal; manual intervention was required" (case-spark-job-pending-not-running.md:Triage)
- Manual boundary -> "- `#MANUAL`: terminate job, rebuild worker pool" (case-spark-job-pending-not-running.md:Safety Boundaries)
- Job id -> "job_id =1488064" (case-spark-job-pending-not-running.md:Triage)
- Stuck signature -> "- `Init:0/1` / long `Terminating`" (case-spark-job-pending-not-running.md:Triage)
- Namespace heuristic -> "- namespace suffix matches `job_id`" (case-spark-job-pending-not-running.md:Triage)
- Verification -> "Verify no zombie namespaces/pods remain and next run can start" (case-spark-job-pending-not-running.md:Verify)
