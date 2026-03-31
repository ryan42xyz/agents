---
metadata:
  kind: case
  status: final
  summary: "Serving pods see MySQL connect timeouts while MySQL itself looks healthy; failures are concentrated on a specific worker node. Key checks are the actual destination address/port (Service DNS vs ServiceSwitch/NodePort), Service/Endpoints, and DNS inside the failing pod/node. Fast mitigation is restarting the serving deployment so pods reschedule onto healthy nodes, suggesting a node-level DNS/network issue."
  tags: ["mysql", "serving", "connect-timeout", "dns", "k8s", "networking", "node"]
  first_action: "Confirm the timeout in serving logs first, then verify MySQL Service/Endpoints and the actual destination address/port (ServiceSwitch/NodePort)"
  related:
    - ./case-mysql-connect-timeout-fp-dns-node.incident.md
    - ./card-aws-k8s-network-triage-chain.md
    - ./card-dns-fast-triage.md
    - ./runbook-dns-url-creation-runbook.md
    - ./runbook-jenkins-selenium-dns-failures.md
    - ./card-site-outage-triage.md
    - ./card-k8s-node-notready-fast-triage.md
    - ./card-kubectl-describe-node-key-signals.md
    - ./card-fp-infra-fast-entrypoints.md
    - ./runbook-mysql-backup-restore-runbook.md

---

# MySQL Connect Timeout: Serving -> MySQL (Suspected Worker DNS/Network Failure)

## TL;DR (Do This First)
1. Confirm error type in serving logs: MySQL `connect timed out` (not auth / refused)
2. Confirm MySQL pod health: `kubectl get pod -n <ns> | grep <mysql-pod>`
3. Identify the actual destination address/port the app uses (Service DNS vs ServiceSwitch/NodePort) and run connectivity tests from the failing pod
4. If failures concentrate on one worker, reschedule serving pods away from that node (restart serving deployment) (`#MANUAL`)

## Safety Boundaries
- Read-only: `get/describe/logs`, check Service/Endpoints, in-pod connectivity probes
- `#MANUAL`: restart the serving deployment pods, cordon/drain nodes, modify ServiceSwitch rules

Rollback/stop conditions (production):
- If rescheduling increases error rate (capacity reduced too far): immediately stop churn; roll back the restart and scale serving to baseline.
- If cordon/drain triggers broader disruption: pause and coordinate with cluster owner; prefer isolating only the suspected node first.



## Related
- [case-mysql-connect-timeout-fp-dns-node.incident.md](./case-mysql-connect-timeout-fp-dns-node.incident.md)
- [card-aws-k8s-network-triage-chain.md](./card-aws-k8s-network-triage-chain.md)
- [card-dns-fast-triage.md](./card-dns-fast-triage.md)
- [card-site-outage-triage.md](./card-site-outage-triage.md)
- [card-k8s-node-notready-fast-triage.md](./card-k8s-node-notready-fast-triage.md)
- [card-kubectl-describe-node-key-signals.md](./card-kubectl-describe-node-key-signals.md)
- [card-fp-infra-fast-entrypoints.md](./card-fp-infra-fast-entrypoints.md)

## Triage
- Confirm error type in serving logs: `connect timed out` (network/DNS/egress path) vs `connection refused` (target/port not listening) vs auth.
- Find failing pods and their nodes; confirm whether it is concentrated on a single worker.
- Confirm the actual destination:
  - Service DNS (`<mysql-service>.<ns>:3306`), or
  - ServiceSwitch/NodePort (`externalIp:externalTargetPort`).
- Verify Kubernetes plumbing: `<mysql-service>` `svc` + `endpoints`.
- Validate DNS for `<mysql-service>.<ns>` inside the failing pod (ideally on the node too).

Representative commands:

```bash
# Logs + failing pod/node
kubectl logs -n <ns> <serving-deployment>-<pod> --tail=100
kubectl get pod -n <ns> <serving-deployment>-<pod> -o wide

# MySQL health and K8s plumbing
kubectl get pod -n <ns> | grep <mysql-pod>
kubectl get svc -n <ns> <mysql-service> -o wide
kubectl get endpoints -n <ns> <mysql-service> -o wide

# If ServiceSwitch is in use, identify externalIp:externalTargetPort for svcName: <mysql-service>
kubectl get ServiceSwitch -n <ns> -o yaml

# DNS inside the failing pod (pick what exists)
nslookup <mysql-service>.<ns>
getent hosts <mysql-service>.<ns>

# TCP connectivity inside the failing pod
nc -vz <mysql-service>.<ns> 3306

# If the app uses a NodePort-style endpoint (example shape), test that too
mysql -h <external-ip> -P <external-target-port> -u <user> -pREDACTED
```

Key decision rule for this case:
- If only pods on a single node fail (unstable DNS lookup, image pulls failing, or TCP timeouts), treat it as a node-level DNS/egress/network failure; reschedule away from the node to stop the bleeding first, then hand off to the node/network owner for root cause.

## Verification
- From a previously failing pod (or after rescheduling): `<mysql-service>.<ns>` resolves and TCP connection to the actual destination succeeds.
- The error signature disappears from serving logs.
- If it is node-level: no MySQL change is needed; simply moving pods stops the timeouts.

Recommended production thresholds:
- Symptom stops: no new connect-timeout log lines for `>= 15m` (same traffic level).
- Blast radius contained: failures were limited to pods on `<suspect-node>`; pods on other nodes were healthy during the incident window.

## Closeout
- Record: failing pod/node, actual destination address (DNS vs ServiceSwitch/NodePort), and the exact error signature.
- If node-level is suspected: cordon/drain the worker (`#MANUAL`) and hand off to the node/network owner.
- Follow-ups: standardize a "DNS + TCP inside pod" troubleshooting toolbox and node-level DNS/egress health signals.

Evidence checklist (minimum, sanitized):
- Failing pod + node (from `kubectl get pod -o wide`)
- Endpoints non-empty (from `kubectl get endpoints`)
- DNS result from failing pod vs healthy pod:
  - `nslookup <mysql-service>.<ns>`
- TCP result from failing pod vs healthy pod:
  - `nc -vz <mysql-service>.<ns> 3306`

## One-line Essence
> Serving-to-MySQL timeouts are caused by broken connectivity/DNS on a worker node; rescheduling pods away from that node stops the bleeding.
