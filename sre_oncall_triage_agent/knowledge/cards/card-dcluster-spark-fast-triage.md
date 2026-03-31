---
metadata:
  kind: runbook
  status: draft
  summary: "Card: DCluster Spark job quick triage - signals for being stuck in Pending/Init/Terminating, and the shortest unblock (terminate the job)."
  tags: ["card", "spark", "dcluster", "k8s", "jobs", "oncall"]
  first_action: "Find job_id first, then locate stuck pods by namespace/job_id"
---

# Card: DCluster Spark Job - Quick Triage

## TL;DR (Do This First)
1. Find `job_id` (alert/MGT link)
2. Confirm pods are stuck (Pending/Init/Terminating)
3. Terminate the job via DCluster (`#MANUAL`)
4. Verify the namespace/pods are cleaned up

## Minimal Commands
```bash
kubectl get pod -A | grep spark | grep <job_id>

#MANUAL
curl -X POST http://<dcluster>/cluster/job/terminate/<job_id>
```

## Further Reading (Deep Doc)
- Full runbook: [runbook-dcluster-spark-job-troubleshooting.md](./runbook-dcluster-spark-job-troubleshooting.md)
