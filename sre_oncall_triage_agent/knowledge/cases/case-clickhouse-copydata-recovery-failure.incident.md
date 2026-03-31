---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-clickhouse-copydata-recovery-failure.md
  title: "ClickHouse CopyData Recovery Misclassified Failed (Validation Too Early)"
  summary: "EN: CopyData recovery automation appeared stuck/failed; status API showed infra stages completed but validation happened before ClickHouse was fully ready, causing transient connection failure and misclassification; improvement is to gate on TCP/SQL readiness instead of StatefulSetReady."
  tags: [clickhouse, kubernetes, ebs, pvc, recovery, automation]
  patterns: [recovery-validation-too-early, statefulset-ready-not-app-ready]
---

# Incident: ClickHouse CopyData Recovery Misclassified Failed (Validation Too Early)

## 1. Incident Overview
- Date: 2026-02-27 (from status API timestamps)
- Severity: TBD
- Duration: TBD
- System: ClickHouse recovery/copy workflow (EBS snapshot -> PV/PVC swap -> restart ClickHouse -> validate)
- Impact: recovery task stalled or reported failure even though service could be recoverable; risk of extending recovery window (user impact: TBD)

## 2. System Context
- Architecture (relevant):
  - Operator/oncall -> CopyData API (status + trigger)
  - AWS EBS snapshot/volume
  - Kubernetes: scale down/up ClickHouse StatefulSet; delete/recreate PV/PVC
- Validation: connect port 9000 and run SQL

## 3. Environment
- Cloud: AWS
- Platform: Kubernetes
- Storage: EBS via PV/PVC
- Database: ClickHouse
- Observability: logs in Grafana (internal link exists in source; omitted here)

## 4. Incident Trigger
- Trigger/symptom:
  - copydata progress stalls for a long time (e.g., `clean` / `data cleaning`)
  - or copydata reports failure even though ClickHouse may already be recoverable (validation ran too early)

## 5. Impact Analysis
- Blast radius: ClickHouse recovery workflow; can delay environment recovery
- Data loss: TBD (workflow includes PV/PVC deletion; high-risk)
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: status API + logs review
- `#MANUAL`: triggering recovery/copy; any step that deletes PV/PVC

## 7. Investigation Timeline
- Query status API for stage + timestamps.
- Correlate with copydata logs to find the first failing stage (clean/stop/start/PV-PVC).
- Distinguish:
  - "task failed" vs
  - "service already recovered but validation is early"

## 8. Root Cause
- Root cause: validation ran before ClickHouse was fully ready; automation treated infra readiness (StatefulSetReady/PodReady) as app readiness, hit transient connection failure, and misclassified the recovery as failed (then could scale down/rollback).
- Symptom vs root cause:
  - Symptom: task stuck/failed near post-start stages
  - Root cause: readiness gate mismatch (infra ready != app ready)

## 9. Resolution
- Operational resolution in notes: "scale up again" and validate ClickHouse readiness after it is truly ready.
- Verification:
  - ClickHouse reachable (TCP 9000)
  - SQL validation succeeds

## 10. Prevention / Improvement
- Replace validation gate:
  - wait until TCP 9000 open
  - AND a minimal SQL like `select 1` succeeds
- Add retry/backoff for early-start transient failures to avoid false negatives.
- Make status stages explicit: infra completion vs app validation.

## 11. Generalizable Lessons
- Kubernetes readiness is not application readiness; treat them as separate states in automation.
- For storage-destructive workflows, keep trigger steps strictly manual and evidence-driven.
- Pattern Card:
  - Pattern name: statefulset-ready-not-app-ready
  - When it happens: stateful workloads with long warmup/metadata loading
  - Fast detection signals: status says "Started" but SQL/connect fails briefly
  - Fast mitigation: wait + retry; avoid auto-rollback on first failure
  - Common pitfalls: validating too early; using only PodReady as readiness

## Tags & Patterns
- Tags: clickhouse, kubernetes, ebs, pvc, recovery, automation
- Patterns: recovery-validation-too-early, statefulset-ready-not-app-ready
- First Action: call status API and identify the first stuck stage + timestamps

## Evidence Mapping
- Symptom -> "CopyData recovery/copy progress stalled for a long time (e.g., stuck at clean/data cleaning)" (case-clickhouse-copydata-recovery-failure.md:Triage)
- Symptom -> "CopyData reported failure even though ClickHouse may already be recoverable (validation ran too early)" (case-clickhouse-copydata-recovery-failure.md:Triage)
- Status snapshot -> "\"overall_progress\": \"88.89%\"," (case-clickhouse-copydata-recovery-failure.md:Triage)
- Stage evidence -> "\"status\": \"Stopping clickhouse\"," (case-clickhouse-copydata-recovery-failure.md:Triage)
- Destructive step -> "\"details\": \"Delete the old pvc and pv, including the pv in the failed state.\"," (case-clickhouse-copydata-recovery-failure.md:Triage)
- Start stage -> "\"details\": \"Start Clickhouse and wait Clickhouse server ready\"" (case-clickhouse-copydata-recovery-failure.md:Triage)
- Root cause framing -> "StatefulSet Ready" (case-clickhouse-copydata-recovery-failure.md:Root Cause (Structured))
- Root cause framing -> "ClickHouse Fully Ready" (case-clickhouse-copydata-recovery-failure.md:Root Cause (Structured))
- Failure mode -> "Connection reset" (case-clickhouse-copydata-recovery-failure.md:Root Cause (Structured))
- Improvement gate -> "wait until:" (case-clickhouse-copydata-recovery-failure.md:Improvements (Minimal Model))
