---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-mysql-connect-timeout-fp-dns-node.md
  title: "MySQL Connect Timeout: Serving -> MySQL (Suspected Worker DNS/Network Fault)"
  summary: "Serving pods hit MySQL connect timeouts while MySQL looked healthy; triage verified the real destination IP/port (ServiceSwitch/NodePort), Service/Endpoints, and in-cluster DNS; restarting the serving deployment to force rescheduling stopped the bleeding, strongly suggesting a worker node DNS/network fault."
  tags: [mysql, serving, connect-timeout, dns, kubernetes, networking, node]
  patterns: [node-dns-causes-db-connect-timeout]
---

# Incident: MySQL Connect Timeout (Serving -> MySQL, suspected worker DNS/network fault)

## 1. Incident Overview
- Date: <YYYY-MM-DD> (local time <TZ>)
- Severity: <SEV-2|SEV-3> (node-scoped degradation)
- Duration: <~minutes> (from first error to stable recovery window)
- System: serving service (namespace `<ns>`) connecting to MySQL
- Impact: serving experienced MySQL connect timeouts; impact limited to pods on one worker node (quantified below)

## 2. System Context
- Architecture (relevant): serving pods -> (ServiceSwitch/Service) -> MySQL
- Dependency: worker node DNS/egress/network path affects both name resolution and outbound connectivity
- Scale: <pods/replicas/traffic-level>

## 3. Environment
- Cloud/Region: <cloud-region>
- Platform: Kubernetes
- Namespace: `<ns>`
- DB: MySQL (pod `<mysql-pod>` observed Running)
- Endpoint type used during debugging: IP + NodePort (per notes)

## 4. Trigger
- Trigger: MySQL connect timeout observed in serving logs (HikariPool init failed; see Evidence Mapping)

## 5. Impact Analysis
- Blast radius: potentially node-scoped (only pods scheduled on a problematic worker)
- User-visible symptoms: elevated error rate / timeouts on a subset of requests routed to affected pods
- Data loss: none indicated (connection failures; no evidence of corruption)
- SLO/SLA breach: <yes/no> (if tracked)
- Quantification (sanitized):
  - affected pods: <n> (all on `<suspect-node>`)
  - unaffected pods: <m> (on other nodes)
  - error rate during window: <baseline_%> -> <peak_%> -> <recovered_%>

## 6. Constraints
- Read-only: get/describe/logs, service/endpoints checks, in-pod probes
- `#MANUAL`: restarting the serving deployment, cordon/drain nodes, ServiceSwitch changes

## 7. Investigation Timeline
- Checked serving logs for MySQL timeout signature.
- Identified which serving pod was failing and which worker node it was scheduled on (`kubectl get pod -o wide`).
- Confirmed MySQL pod appears healthy (`<mysql-pod>` is Running).
- Retrieved MySQL routing/config via `ServiceSwitch` and/or `Service/Endpoints`.
- Captured `<mysql-service>` endpoints (`kubectl get endpoints -n <ns> <mysql-service> -o wide`) to identify the real destination.
- Tested connectivity via IP + NodePort using `curl` and `mysql` client.
- Validated DNS in-cluster:
  - temporary debug pod approach failed due to image pull failure
  - installed `dnsutils` in an existing pod and ran `nslookup kubernetes.default`
- Validated `<mysql-service>.<ns>` name resolution and compared failing vs healthy pods/nodes.
- Mitigation: restarted serving deployment pods to reschedule away from suspected bad worker.

Timeline (sanitized):
- T0: first connect-timeout signature observed in logs.
- T0+<m>: identified failures concentrated on `<suspect-node>`.
- T0+<m>: verified MySQL healthy and endpoints non-empty.
- T0+<m>: DNS+TCP probes:
  - failing pod: DNS <ok/fail>, TCP <ok/fail>
  - healthy pod: DNS ok, TCP ok
- T0+<m> `#MANUAL`: restarted serving deployment to reschedule away from `<suspect-node>`.
- T0+<m>: verification: errors stopped for >= 15m.

## 8. Root Cause
Root cause classification (evidence-backed):
- Direct cause: node-scoped DNS/egress/network fault caused connect timeouts from pods scheduled on `<suspect-node>`.
- Evidence:
  - Failures were concentrated on one node; pods on other nodes were healthy in the same window.
  - DB pod was Running and endpoints were present.
  - Rescheduling away from `<suspect-node>` stopped the symptom without DB changes.
Root cause (deep) pending node/network owner investigation (node logs, CNI, DNS cache, conntrack, egress).

Alternative hypothesis (to validate if it repeats):
- The ServiceSwitch routing path for `<mysql-service>` (svcPort 3306 -> externalTargetPort <node-port>) was not reachable from a subset of worker nodes due to node-level routing / policy drift.


## 9. Mitigation
- Restart serving deployment pods (`#MANUAL`) to force rescheduling.
- Verify MySQL connectivity and absence of connect timeout logs.

Action log (production-grade):
- `#MANUAL` <time> <owner>: restarted `<serving-deployment>` (goal: move pods off `<suspect-node>`). Rollback: scale back to baseline if capacity loss increases errors.
- Optional follow-up `#MANUAL`: cordon/drain `<suspect-node>` after confirmation (goal: prevent recurrence while root cause is investigated).

## 10. Prevention / Improvement
- Add serving-side DB connectivity checks (DNS -> TCP -> auth) and expose as SLI.
- Add node DNS/egress monitoring (CoreDNS metrics, node-local DNS cache, packet loss).
- Add a runbook branch: when debug pod image pull fails + DNS issues co-occur, treat as node-level network fault; cordon/drain and investigate.
- Add an explicit isolation experiment in the runbook: failing pod -> node -> endpoints -> test from pod and from node to separate node-scoped vs pod-scoped failures.

## 11. Generalizable Lessons
- DB connect timeout is often not the DB: confirm DB pod health, then validate the network and DNS layers.
- If only a subset of pods fail and rescheduling fixes it, suspect node-scoped faults.
- When debug pod cannot pull a tiny image, it can be a valuable signal of node egress/DNS issues.
- Pattern Card:
  - Pattern name: node-dns-causes-db-connect-timeout
  - When it happens: worker DNS/egress config is broken or intermittent
  - Fast detection signals: connect timeouts from pods on specific nodes; DNS lookup failures
  - Fast mitigation: reschedule pods; cordon/drain node
- Common pitfalls: restarting DB first; ignoring Service/Endpoints checks

## Tags & Patterns
- Tags: mysql, serving, connect-timeout, dns, kubernetes, networking, node
- Patterns: node-dns-causes-db-connect-timeout
- First Action: confirm the timeout in serving logs, then check MySQL endpoints and DNS inside the failing pod

## Evidence Mapping
- Symptom -> "Serving (namespace `<ns>`) connects to MySQL and hits connect timeout." (case-mysql-connect-timeout-fp-dns-node.md:Trigger / Symptom)
- MySQL pod health -> "<mysql-pod> Running" (case-mysql-connect-timeout-fp-dns-node.md:Trigger / Symptom)
- Error signature -> "Socket fail to connect to host:<mysql-service>.<ns>, port:3306. connect timed out" (case-mysql-connect-timeout-fp-dns-node.md:Trigger / Symptom)
- Serving log command -> "kubectl logs <serving-deployment>-... -n <ns> --tail=100" (case-mysql-connect-timeout-fp-dns-node.md:Check logs)
- ServiceSwitch check -> "kubectl get ServiceSwitch -n <ns> -o yaml" (case-mysql-connect-timeout-fp-dns-node.md:Confirm endpoint)
- ServiceSwitch mapping -> "svcName: <mysql-service>" (case-mysql-connect-timeout-fp-dns-node.md:ServiceSwitch snippet)
- ServiceSwitch mapping -> "externalTargetPort: <node-port>" (case-mysql-connect-timeout-fp-dns-node.md:ServiceSwitch snippet)
- NodePort probe -> "curl <internal-ip>:<node-port>" (case-mysql-connect-timeout-fp-dns-node.md:Connectivity probes)
- MySQL client probe -> "mysql -h <internal-ip> -P <node-port> -u <user> -pREDACTED" (case-mysql-connect-timeout-fp-dns-node.md:Connectivity probes)
- DNS debug pod attempt -> "kubectl run dns-test --rm -it --image=busybox:1.36 --restart=Never -- nslookup kubernetes.default" (case-mysql-connect-timeout-fp-dns-node.md:DNS validation)
- DNS tools fallback -> "sudo apt install dnsutils" (case-mysql-connect-timeout-fp-dns-node.md:DNS validation)
