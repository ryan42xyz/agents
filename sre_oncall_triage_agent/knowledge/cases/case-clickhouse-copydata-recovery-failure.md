---
metadata:
  kind: case
  status: final
  summary: "Troubleshoot ClickHouse cross-cluster copy/recovery (copydata) failures: use the status API plus logs to locate the first failing stage (clean/stop/start/PV-PVC), and avoid destructive rollback/rerun triggered by a 'false failure' caused by verifying too early."
  tags: ["clickhouse", "copydata", "recovery", "ebs", "pvc"]
  first_action: "Call the copydata status API first to find the stuck stage"
  related:
    - ./case-clickhouse-copydata-recovery-failure.incident.md
    - ./reference-data-copy-snapshot-backup-restore.md
    - ./card-clickhouse-disk-space-fast.md
    - ./runbook-database-incident-troubleshooting.md
    - ./runbook-clickhouse-backfill-data-extraction.md

---

# ClickHouse CopyData Recovery Failure: Troubleshooting Notes

## TL;DR (Do This First)
1. Query the status API: confirm the current stage + timestamps
2. Align with copydata logs: find the first failing stage (clean/stop/start/PV-PVC)
3. Verify ClickHouse directly (TCP 9000 + simple SQL) to distinguish "task failed" vs "service recovered but verification was too early"
4. Treat any action that triggers recovery / deletes PV/PVC as `#MANUAL`

## Safety Boundaries
- Prefer read-only diagnostics: status API + logs + Kubernetes read-only queries
- `#MANUAL` (write/destructive): trigger recovery (`POST`), delete PV/PVC, scale StatefulSet, any data-path cleanup



## Related
- [case-clickhouse-copydata-recovery-failure.incident.md](./case-clickhouse-copydata-recovery-failure.incident.md)
- [reference-data-copy-snapshot-backup-restore.md](./reference-data-copy-snapshot-backup-restore.md)
- [card-clickhouse-disk-space-fast.md](./card-clickhouse-disk-space-fast.md)
- [runbook-database-incident-troubleshooting.md](./runbook-database-incident-troubleshooting.md)

## Triage
- Start from the status API: identify the first stage that stops progressing (clean/stop/start/PV-PVC).
- Use copydata pod logs to locate the first failure.
- Treat "task failed" as a control-plane signal only; verify ClickHouse data-plane readiness separately before any rollback/rerun.

Status API (primary entrypoint, internal):

```bash
curl --location \
  'http://<internal-copydata-service>/v1/copy/clickhouse/recovery/<env>/status?all=True'
```

Logs (copydata pod):

`<internal-logs-link>`

If you need to (re-)trigger recovery:

```bash
#MANUAL
curl --location --request POST \
  'http://<internal-copydata-service>/v1/api/copy/cross/cluster/clickhouse' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "sourceCluster": "<source-cluster>",
    "destinationNamespace": "<destination-namespace>",
    "service": "<service>",
    "sourceNamespace": "<source-namespace>",
    "fsType": "<fs-type>"
  }'
```

Key decision rule for this case:
- copydata may be marked failed because verification ran before ClickHouse became fully ready; if TCP 9000 is reachable and a simple query succeeds, treat it as a "false failure" and avoid destructive reruns.

## Verification
- Status keeps progressing (not stuck in one stage for a long time without log evidence)
- ClickHouse pods become Ready and accept connections
- Minimal verification passes (connect to 9000 and run a simple query like `select 1`)

## Closeout
- Record: stuck stage, status API timestamps, and the first failing log line
- If it was a "false failure" (ClickHouse actually recovered), record proof (TCP 9000 + simple SQL) and whether any rollback happened
- Follow-up: change verification to wait for app readiness (TCP 9000 open and `select 1` succeeds) before declaring failure

## One-line Essence
Recovery may have succeeded but got marked failed due to early verification; before acting on a copydata failure, independently verify ClickHouse readiness.
