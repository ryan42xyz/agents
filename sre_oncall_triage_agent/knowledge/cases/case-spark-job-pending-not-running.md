---
metadata:
  kind: case
  status: final
  summary: "Oncall handling for Spark/Luigi jobs stuck in Pending (never reaching Running): extract job_id from alerts/logs, confirm the stuck state in K8s (Pending/Init/Terminating), stop the bleeding by terminating the job via DCluster, recycle the worker pool if needed, and finally verify cleanup completion."
  tags: ["spark", "luigi", "dcluster", "jobs"]
  first_action: "Find job_id first, confirm stuck pods, then terminate via DCluster (`#MANUAL`)"
  related:
    - ./case-spark-job-pending-not-running.incident.md
    - ./card-dcluster-spark-fast-triage.md
    - ./runbook-k8s-pod-pending-asg-cluster-autoscaler.md
---

# Spark Job Pending / Not Running - Oncall Case

## TL;DR (Do This First)
1. Get `job_id` from the alert or logs.
2. Confirm the job namespace/pods are stuck (never reaches `Running`).
3. Terminate the job via DCluster (`#MANUAL`) to release resources.
4. If many jobs are stuck, recycle the Spark worker pool (`#MANUAL`).
5. Verify pods/namespaces are cleaned up and the next schedule can start normally.

## Safety Boundaries
- Read-only: `get/describe/logs`.
- `#MANUAL`: terminate jobs; scale worker pool (may affect scheduling).



## Related
- [case-spark-job-pending-not-running.incident.md](./case-spark-job-pending-not-running.incident.md)
- [card-dcluster-spark-fast-triage.md](./card-dcluster-spark-fast-triage.md)

## Triage
Goal: (1) locate `job_id`, (2) prove it is stuck in Pending/Init/Terminating, (3) decide whether to only terminate the job or also recycle the worker pool.

### Step 1: Get `job_id`

Extract it from the alert/log context (often the namespace suffix).

```
job_id =1488064
```


### Step 2: Confirm it is stuck in Kubernetes (Pending/Init/Terminating)

```bash
kwestprodb get pod -A | grep spark | grep s-prod # all of jobs

kwestprodb get pod -A | grep spark | grep 1488064

```

Common stuck patterns:
- Pod stays in `Init:0/1` for a long time.
- Pod stays in `Terminating` for a long time.
- Namespace ends with `job_id`.

---

### Step 3: Decide the action

- If only one or two jobs are stuck: terminate the `job_id` first.
- If many jobs are stuck or scheduling is clearly unhealthy: terminate stuck jobs first, then recycle the worker pool (only when there are no healthy Running jobs).

## Verification

You must verify after every `#MANUAL` step.

### Terminate a Spark job (required)

Reference (internal): `<internal-wiki-link>`

```bash
#MANUAL
curl -X POST \
http://<dcluster-endpoint>/cluster/job/terminate/<job_id>

```

If you lack permissions, follow your standard access path (e.g., jumpserver).

Verify job pods are gone:

```bash
kwestprodb get pod -A | grep spark | grep 1488064

```

### (Optional) Recycle Spark worker pool (only if needed)

Before scaling workers to 0, confirm there are no healthy Spark jobs currently running to avoid killing in-flight work.

```bash
kwestprodb get pod -A | grep spark | grep s-prod
```


Continue only after you confirm there are no `Running` spark-agents in customer namespaces.

---

#### Scale workers to 0

```bash
#MANUAL
kwestprodb scale sts -n spark-long-living-cluster spark-worker --replicas=0

```

Wait until desired/current is `0/0`.

```bash
kwestprodb get sts -n spark-long-living-cluster
# spark-worker 0/0

```

---

#### Scale workers back up

```bash
#MANUAL
kwestprodb scale sts -n spark-long-living-cluster spark-worker --replicas=50

```

Wait until desired/current is `50/50`.

```bash
kwestprodb get sts -n spark-long-living-cluster
# spark-worker 50/50

```

---

## Closeout
- Confirm alerts are cleared and the next scheduled run can start normally.
- Record `job_id`, timestamp, commands executed, and whether the worker pool was recycled.
- If it repeats, follow up on Spark master/worker pool stability.

## One-line Essence

If a Spark/Luigi job never reaches `Running` after creation, terminate the stuck `job_id` first (recycle workers only if needed) and verify namespaces/pods are cleaned up.
