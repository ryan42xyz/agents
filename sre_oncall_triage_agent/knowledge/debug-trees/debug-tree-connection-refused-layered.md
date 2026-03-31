---
metadata:
  kind: debug-tree
  status: stable
  summary: "Layered connection-refused triage: Client → DNS → LB → Ingress → Service → Pod"
  tags: ["connection-refused", "networking", "clickhouse", "ingress", "dns", "nlb"]
  first_action: "Classify error: connection refused vs timeout"
  routing_cluster: "Cluster 1 — Routing/DNS/Ingress"
  related:
    - cases/case-clickhouse-connection-refused-troubleshooting.md
    - patterns/pattern-aws-k8s-networking-troubleshooting-pattern.md
    - checklists/checklist-aws-lb-ingress-troubleshooting-checklist.md
    - references/reference-request-routing-flow.md
---

# Debug Tree: Layered Connection-Refused Triage

## Match Condition

- Client reports `connection refused` (TCP RST), NOT `connection timeout`
- Target is a TCP service exposed through the K8s ingress path (NLB → NodePort → ingress-nginx → Service → Pod)
- Service was previously reachable, or is a new setup that never worked externally
- "Refused" means nothing is listening at that IP:port; distinct from "timeout" which means packets dropped/routed nowhere

## Required Signals

| Signal | Required | Source |
|--------|----------|--------|
| host | yes | failing endpoint hostname or IP |
| port | yes | failing endpoint port |
| namespace | yes | K8s namespace of the backend service |
| service_name | yes | K8s Service name for the backend |
| ingress_controller_pod | recommended | ingress-nginx controller pod name |
| backend_pod | recommended | backend pod name (e.g., ClickHouse pod) |

## Steps

### Step 1: Classify error — refused vs timeout

- **Tool**: `nc` (from client or debug pod)
- **Query**: `nc -vz {host} {port}`
- **Extract**: error message — "connection refused" vs "connection timed out"
- **Branch**:
  - `connection refused` → CONTINUE Step 2
  - `connection timed out` → FINDING: "Timeout indicates routing/LB/network issue, not a listener issue" → **ESCALATE** (different triage path: routing/LB/SG/NACL)
  - Connection succeeds → FINDING: "Connectivity OK from this vantage point" → **MANUAL** (re-test from the original failing client; check source-dependent routing)
- **on_error**:
  - timeout → RETRY_ONCE
  - other → ESCALATE

### Step 2: Verify DNS resolution

- **Tool**: `nslookup` / `dig`
- **Query**: `nslookup {host}` or `dig +short {host}`
- **Extract**: resolved IP address(es)
- **Branch**:
  - Resolves to expected IP → CONTINUE Step 3
  - NXDOMAIN or wrong IP → FINDING: "DNS resolution broken: got {actual} instead of {expected}" → **ESCALATE** (fix DNS record / split-horizon config)
  - No response → FINDING: "DNS server unreachable" → **ESCALATE** (DNS infrastructure issue)
- **on_error**:
  - timeout → RETRY_ONCE
  - other → ESCALATE

### Step 3: Check Service endpoints

- **Tool**: `kubectl`
- **Query**: `kubectl get endpoints {service_name} -n {namespace} -o wide`
- **Extract**: endpoint addresses and ready status
- **Branch**:
  - Endpoints populated with Ready addresses → CONTINUE Step 5 (skip to ingress check)
  - `ENDPOINTS <none>` → CONTINUE Step 4 (diagnose missing endpoints)
  - Endpoints exist but NotReady → FINDING: "Endpoints exist but not Ready — readiness probe failing" → **MANUAL** (check readiness probe config and pod logs)
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

### Step 4: Diagnose missing endpoints — label/selector mismatch

- **Tool**: `kubectl`
- **Query**:
  ```bash
  kubectl get svc {service_name} -n {namespace} -o jsonpath='{.spec.selector}'
  kubectl get pods -n {namespace} --show-labels
  ```
- **Extract**: Service selector labels vs actual pod labels
- **Branch**:
  - Label mismatch found (e.g., `clickhouse.altinity.com/ready=no` vs selector expecting `ready=yes`) → FINDING: "Operator did not refresh ready label after pod restart; selector mismatch causes empty endpoints" → **MANUAL** (rollout restart StatefulSet: `kubectl rollout restart statefulset {sts_name} -n {namespace}`)
  - Labels match but still no endpoints → FINDING: "Labels match but endpoints empty — possible readiness gate or EndpointSlice issue" → **ESCALATE** (check readiness gates, EndpointSlice controller)
  - No pods matching selector exist → FINDING: "No pods match Service selector" → **ESCALATE** (check StatefulSet/Deployment status)
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

### Step 5: Check ingress-nginx TCP listener

- **Tool**: `kubectl exec`
- **Query**: `kubectl exec -n ingress-nginx {ingress_controller_pod} -- ss -lntp`
- **Extract**: whether the target TCP port appears in the listener list
- **Branch**:
  - Port found in listener list → CONTINUE Step 7 (skip to backend bind check)
  - Port NOT in listener list → CONTINUE Step 6 (diagnose tcp-services config)
  - Exec fails (pod not found / CrashLoopBackOff) → FINDING: "Ingress controller pod unhealthy" → **ESCALATE** (check ingress-nginx pod status and logs)
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

### Step 6: Check tcp-services ConfigMap and controller args

- **Tool**: `kubectl`
- **Query**:
  ```bash
  kubectl get cm tcp-services -n ingress-nginx -o yaml
  kubectl get deploy ingress-nginx-controller -n ingress-nginx -o yaml | grep tcp-services
  ```
- **Extract**: (1) ConfigMap entries for the target port, (2) whether `--tcp-services-configmap` arg is present in controller deployment
- **Branch**:
  - ConfigMap exists but `--tcp-services-configmap` arg missing from controller → FINDING: "tcp-services ConfigMap exists but controller not configured to load it" → **MANUAL** (add `--tcp-services-configmap=ingress-nginx/tcp-services` to controller args + rollout restart controller)
  - ConfigMap missing entry for target port → FINDING: "tcp-services ConfigMap does not include port {port}" → **MANUAL** (add port mapping to ConfigMap)
  - Both present and correct → FINDING: "Config looks correct but controller not listening — may need restart" → **MANUAL** (rollout restart ingress-nginx controller, then re-verify with Step 5)
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

### Step 7: Check backend process bind address

- **Tool**: `kubectl exec`
- **Query**: `kubectl exec -n {namespace} {backend_pod} -- ss -lntp`
- **Extract**: bind addresses for the service port
- **Branch**:
  - Listening on `0.0.0.0` or pod IP → FINDING: "Full path verified: DNS/Endpoints/Ingress/Backend all OK. Connection refused may be intermittent or source-dependent." → **MANUAL** (re-test from original client, check NLB target group health and security groups)
  - Listening only on `127.0.0.1` → FINDING: "Backend binds to localhost only — external traffic will always be refused even with healthy NLB/ingress/endpoints" → **MANUAL** (change backend listen/bind config to `0.0.0.0` or pod IP)
  - Process not listening at all → FINDING: "Backend process not listening on expected port" → **ESCALATE** (check pod logs for crash/startup failure)
- **on_error**:
  - command fails → ESCALATE (cluster access issue)
  - other → ESCALATE

## Resolution Template

```markdown
## Conclusion
- verdict: {RESOLVED | ESCALATE | MANUAL}
- confidence: {high | medium | low}
- evidence_chain: [Step 1: refused confirmed → Step 2: DNS OK → Step 3: endpoints {status} → ... → Step N: root cause]
- root_cause: {description}
- branch: {A: ingress tcp-services not loaded | B: operator label stale / empty endpoints | C: backend binds localhost only}
- fix_applied: {description of fix or "pending #MANUAL approval"}
- verification:
  - nc -vz {host} {port} succeeds from external/VPC
  - kubectl get endpoints {service_name} -n {namespace} shows Ready endpoints
  - ingress-nginx ss -lntp shows port in listener list
  - backend ss -lntp shows bind on 0.0.0.0 or pod IP
- follow_up:
  - [ ] Add alert: Service endpoints = none for > 2 min on stateful services
  - [ ] Add smoke test: post-restart endpoint readiness check in deploy pipeline
  - [ ] Document operator label refresh behavior in runbook
```

## Historical Cases

- **ClickHouse connection refused (2026-03 layered triage)**: External client hit "connection refused" on ClickHouse port. Walk revealed two root causes: (Branch A) ingress-nginx tcp-services ConfigMap existed but `--tcp-services-configmap` arg was missing from controller; (Branch B) after pod restart, Altinity Operator did not refresh `clickhouse.altinity.com/ready` label, causing empty endpoints. Branch B was the primary cause in the live incident. Fix: rollout restart StatefulSet to trigger label refresh. Verdict: RESOLVED.
