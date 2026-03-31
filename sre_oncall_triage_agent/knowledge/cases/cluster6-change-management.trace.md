---
metadata:
  kind: structured-triage-trace
  status: final
  sources:
    - case-qa-deployment-failure-disk-cleanup.md
    - case-aws-asg-scale-out-node-join-failure.md
    - runbooks/runbook-k8s-upgrade-plan-runbook.md
  schema_version: "0.1"
  tags: ["change-management", "deployment", "upgrade", "rollback", "regression"]
  failure_domain: "change management / upgrades"
  cluster: "Cluster 6 — Change management, upgrades, post-change regression"
---

# Structured Triage Trace: Cluster 6 — Change Management / Post-Change Regression

---

## Signal

```
signals:
  A  deployment fails or services degrade after a recent change
  B  cluster upgrade regression (component version skew, API deprecation)
  C  QA/dev environment broken after scheduled cleanup/maintenance job
  D  ASG node join failure after Launch Template / AMI change

→ cluster: Cluster 6 (Change Management)
→ reason:  the defining feature is temporal correlation with a change event.
           the change IS the suspect — triage starts by confirming the change window.
```

### Routing Logic

```
IF   incident_start correlates with recent_deploy OR config_change OR maintenance_window
THEN triage_path = change_regression_analysis
     first_action = confirm change window and scope before any investigation

IF   node_join_failure AND recent_LT_or_AMI_change
THEN first_mitigation = roll back Launch Template (#MANUAL)
     reason: faster to restore capacity than to diagnose new config

IF   QA_env_broken AND recent_cleanup_job_ran
THEN first_action = confirm cleanup window + check dependency order
     fix_order: storage/DB first → upper-layer services second

IF   k8s_upgrade AND component_regression
THEN triage_path = version_skew_check
     first_action = kubectl version + component version matrix check
```

---

## Decision Trace

| # | Action | Tool/Method | Observation | Inference | Confidence |
|---|--------|-------------|-------------|-----------|------------|
| 1 | Confirm change window | git log / deploy log / maintenance calendar | Deploy/upgrade/cleanup ran T-X before incident | Change is the prime suspect | 0.85 |
| 2 | Scope the blast radius | What changed? Which components? Which clusters? | LT version changed / k8s minor bump / cleanup job scope | Determines which services/nodes could be affected | 0.80 |
| 3 | Find first broken dependency | Events + logs on failing components | DB/storage layer failing → upper services cascading | Fix in dependency order; don't start at UI layer | 0.90 |
| 4 | Assess rollback viability | Is the change reversible? Is there a known-good state? | LT has previous version / git has last-green tag | Roll back first if capacity/service is impacted | 0.85 |
| 5 | Roll back vs fix-forward | Is root cause identified? Is fix safe to deploy? | Root cause unknown AND users impacted → rollback | Roll back to restore service; fix-forward only when safe | 0.90 |
| 6 | Verify after rollback/fix | Metrics, pod status, smoke tests | Services recovering; no cascading failures | Mitigation effective; move to prevention | 0.90 |

---

## Evidence Chain

```
key_insight: change = temporal correlation is necessary but not sufficient
  must confirm: change_window aligns with incident_onset
  must rule out: independent failure coinciding with change window

rollback_decision_rule:
  IF root_cause_identified AND fix_is_safe → fix-forward
  IF root_cause_unknown AND users_impacted → roll back first, investigate after

dependency_order_rule:
  storage/DB must be healthy before upper-layer services can recover
  deploying UI/analytics before DB is ready → cascading failures, wastes time

version_skew_pattern (k8s upgrade):
  component A at version N+1, component B at version N → API mismatch
  always check: kubelet version, kube-proxy version, CNI version, CRD API versions
  common regression: deprecated API in upgraded apiserver still used by old manifests
```

---

## Triage Policy (Extracted)

```yaml
policy_name: change-regression-triage

trigger:
  condition: incident_onset correlates with change_window

steps:
  - id: step_1
    action: confirm_change_window
    tool: deploy_log OR git_log OR maintenance_calendar
    gate: IF no change found in window → route to other cluster (not change regression)
    on_confirmed: continue

  - id: step_2
    action: scope_blast_radius
    tool: deploy_log + kubectl get nodes/pods
    signal: which components, namespaces, nodes are affected
    gate: document scope before taking any action

  - id: step_3
    action: find_first_broken_dependency
    tool: kubectl events + logs
    command: "kubectl get events -A --sort-by=.lastTimestamp | tail -50"
    gate: IF storage/DB failing → fix storage/DB first (step_4a)
    on_upper_layer_only: check if dependency is actually healthy

  - id: step_4a
    action: rollback_change
    type: "#MANUAL"
    when: root_cause unknown AND service impacted
    examples:
      - LT: "aws autoscaling update-auto-scaling-group --launch-template ..."
      - k8s: "helm rollback <release> <revision>"
      - deployment: "kubectl rollout undo deployment/<name>"
    gate: always requires explicit approval

  - id: step_4b
    action: fix_forward
    type: "#MANUAL"
    when: root_cause identified AND fix is safe AND tested in lower env
    gate: deploy in QA/staging first; verify before promoting

  - id: step_5
    action: restore_in_dependency_order
    rule: storage → DB → middleware → application → UI
    gate: verify each layer before proceeding to the next

  - id: step_6
    action: verify_recovery
    tool: kubectl get pods + smoke tests + metrics
    criteria:
      - no new error events for 15+ min
      - all affected pods in Running/Ready
      - error rate back to baseline

human_gates:
  - all rollback actions
  - all redeploy/fix-forward actions
  - any cleanup job schedule modification
  - k8s upgrade continuation after regression found

verification:
  - services stable for >= 15 min post-fix
  - no cascading failures in downstream dependencies
  - alerts cleared
  - each #MANUAL action logged with who/when/what/why
```

---

## Verifier Checklist

Before closing:

- [ ] Change window confirmed and correlated with incident onset
- [ ] Blast radius documented (which components, which clusters)
- [ ] All failed dependencies restored in correct order (storage → DB → app → UI)
- [ ] No new error events for 15+ min
- [ ] All pods in affected namespaces are Running/Ready
- [ ] Rollback or fix-forward action logged with rationale
- [ ] Follow-up items filed (CI validation gate, cleanup job guardrails, upgrade checklist)

---

## Pattern Cross-Reference

```
cluster_rule:
  "In Cluster 6, the change is always the first suspect.
   Confirm the change window before investigating symptoms.
   Roll back to restore service first; investigate root cause after service is stable.
   Fix in dependency order: you cannot rebuild a house on a broken foundation."

anti_patterns:
  - Investigating root cause while users are impacted (should rollback first)
  - Redeploying upper-layer services before DB/storage is healthy
  - Skipping version skew check after k8s upgrade
  - Treating cleanup job damage as 'random failure' without checking the schedule

cluster_relationships:
  Cluster 6 upgrades often trigger Cluster 1 (routing regression),
  Cluster 2 (scheduling after node pool changes), and
  Cluster 3 (stateful system restart under pressure).
  After confirming a change regression, check all three downstream clusters.
```
