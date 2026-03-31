---
metadata:
  kind: structured-triage-trace
  status: final
  source: case-clickhouse-connection-refused-troubleshooting.incident.md
  schema_version: "0.1"
  tags: ["clickhouse", "kubernetes", "networking", "connection-refused", "endpoints"]
  failure_domain: "networking / routing"
  cluster: "Cluster 1 — Routing, DNS, ingress, edge path"
---

# Structured Triage Trace: ClickHouse Connection Refused (Layered Hop Triage)

---

## Signal

```
alert:     external client hits "connection refused" on ClickHouse port
signal:    connection refused (not timeout)
→ cluster: Cluster 1 (Routing / DNS / Ingress / Edge)
→ reason:  "refused" means nothing is listening at that IP:port;
           distinct from "timeout" which means packet is dropped/routed nowhere
```

### Routing Logic

```
IF   error_class == connection_refused
THEN triage_path = hop_by_hop_layer_walk
     start_from  = client_side (not backend)
     stop_at     = first broken hop

IF   error_class == connection_timeout
THEN triage_path = routing / LB / network (different path, not this trace)
```

---

## Decision Trace

Walk stops at first broken hop. Remaining hops are skipped once root cause is localized.

| # | Hop | Action | Tool/Method | Observation | Inference | Confidence |
|---|-----|--------|-------------|-------------|-----------|------------|
| 1 | classify | Confirm refused vs timeout | `nc -vz <host> <port>` | "connection refused" | Nothing listening at target IP:port; not a routing issue | 0.90 |
| 2 | [B] DNS | Verify DNS resolves correctly | `nslookup` / `dig +short` | Resolves to expected IP | DNS not the issue | 0.85 |
| 3 | [C] LB | NLB reachable, TG healthy | `nc -vz <host> <port>` from VPC EC2 | Still refused from VPC | NLB passes through; problem is behind it | 0.80 |
| 4 | [E] ingress | Is controller listening on TCP port | `kubectl exec ingress-nginx -- ss -lntp` | Port NOT in listener list | ingress-nginx not serving this TCP port | 0.90 |
| 5 | [E] ingress config | Check tcp-services ConfigMap loaded | `kubectl get cm tcp-services -oyaml` + check controller args | ConfigMap exists but controller arg `--tcp-services-configmap` absent or not refreshed | Root cause branch A: tcp-services not loaded | 0.90 |
| 6 | [G] endpoints | Check Service endpoints | `kubectl get endpoints <svc>` | `ENDPOINTS <none>` | Service has no ready backends — alternative root cause branch | 0.95 |
| 7 | [G] label match | Check pod label vs selector | `kubectl get pod --show-labels` vs `kubectl get svc -oyaml` | Pod label `clickhouse.altinity.com/ready=no` after restart | Operator did not refresh ready label post-restart → selector mismatch → no endpoints | 0.98 |

### Branch Decision

```
Branch A (ingress tcp-services not loaded):
  trigger:  "always broken" or "after controller restart/upgrade"
  evidence: controller not listening on port (step 4) + controller arg missing (step 5)
  fix:      add --tcp-services-configmap arg + rollout restart controller (#MANUAL)

Branch B (endpoints = none, operator label stale):
  trigger:  "worked before, suddenly stopped" after pod restart
  evidence: endpoints <none> (step 6) + ready=no label (step 7)
  fix:      kubectl rollout restart statefulset <chi-name> -n <ns> (#MANUAL)
            workaround: use pod DNS directly to confirm CH is alive

Branch C (CH binds only 127.0.0.1):
  trigger:  "never worked" from external
  evidence: endpoints exist, but `ss -lntp` in CH pod shows only 127.0.0.1
  fix:      change CH bind config to 0.0.0.0 / pod IP (#MANUAL)
```

---

## Evidence Chain

```
root_cause_primary (branch B — "suddenly stopped"):
  operator_did_not_refresh_ready_label
    mechanism: Altinity Operator sets clickhouse.altinity.com/ready=yes post-startup
               but after abnormal restart (OOMKill/drain/crash) it did not re-evaluate
    evidence:  step 6 (endpoints <none>) + step 7 (ready=no label on pod)

root_cause_secondary (branch A — "never worked externally"):
  ingress_nginx_not_listening_on_tcp_port
    mechanism: tcp-services ConfigMap exists but controller not loading it
    evidence:  step 4 (ss shows no listener) + step 5 (controller arg missing)

ruled_out:
  - DNS failure (step 2: resolves correctly)
  - NLB health failure (step 3: refused from VPC, bypasses NLB correctly)
  - CH process crash (step 7: pod running, just label mismatch)

key_principle:
  "refused = nothing listening; timeout = packet lost in transit.
   LB health can be green while application is unreachable.
   Always validate runtime state (ss, endpoints) vs spec state (ConfigMap, labels)."
```

---

## Triage Policy (Extracted)

```yaml
policy_name: connection-refused-layered-triage

trigger:
  alert: connection_refused on stateful TCP service
  condition: external client gets refused (not timeout)

steps:
  - id: step_1
    action: classify_error
    tool: nc
    command: "nc -vz <host> <port>"
    gate: IF timeout → exit to timeout triage path (different policy)
    on_refused: continue

  - id: step_2
    action: check_dns
    tool: nslookup
    gate: IF NXDOMAIN or wrong IP → fix DNS record
    on_ok: continue

  - id: step_3
    action: check_endpoints
    tool: kubectl
    command: "kubectl get endpoints <svc> -n <ns>"
    gate: IF endpoints == none → branch to label/selector check (step_4a)
    on_populated: continue to ingress check (step_4b)

  - id: step_4a
    action: check_pod_labels_vs_selector
    tool: kubectl
    command: "kubectl get pod --show-labels && kubectl get svc -oyaml"
    gate: IF selector mismatch (e.g. ready=no) → root_cause = operator label stale
    fix: "kubectl rollout restart statefulset <chi-name> (#MANUAL)"

  - id: step_4b
    action: check_ingress_listener
    tool: kubectl exec
    command: "kubectl exec ingress-nginx-controller -- ss -lntp"
    gate: IF port not in listener → branch to tcp-services check (step_5)
    on_listening: continue to backend check

  - id: step_5
    action: check_tcp_services_loaded
    tool: kubectl
    command: "kubectl get cm tcp-services && kubectl get deploy ingress-nginx-controller -oyaml | grep tcp"
    gate: IF configmap missing or arg absent → root_cause = ingress config not loaded
    fix: "add --tcp-services-configmap arg + rollout restart (#MANUAL)"

  - id: step_6
    action: check_ch_bind_address
    tool: kubectl exec
    command: "kubectl exec <ch-pod> -- ss -lntp"
    gate: IF only 127.0.0.1 → root_cause = CH bind localhost only
    fix: "change CH listen_host config (#MANUAL)"

human_gates:
  - rollout restart of ingress-nginx controller
  - rollout restart of ClickHouse StatefulSet
  - any change to ClickHouse bind/listen configuration
  - any change to tcp-services ConfigMap or controller args
```

---

## Verifier Checklist

Before closing as resolved:

- [ ] `nc -vz <host> <port>` from external / VPC succeeds
- [ ] `kubectl get endpoints <svc>` shows non-empty Ready endpoints
- [ ] `kubectl get pod --show-labels` shows `clickhouse.altinity.com/ready=yes`
- [ ] ingress-nginx controller `ss -lntp` shows port in listener list
- [ ] ClickHouse pod `ss -lntp` shows bind on `0.0.0.0` or pod IP (not only `127.0.0.1`)
- [ ] Every `#MANUAL` action is logged with who/when/what

---

## Blast Radius

```
action_surface:  read-only until step 4a/4b branch decision
human_gates:     rollout restart of statefulset (branch B), controller restart (branch A)
rollback_path:   statefulset restart is reversible; CH config change needs config rollback
escalation:      if endpoints absent and operator never sets ready=yes → escalate to CH operator owner
```

---

## Closeout Artifact

```
Status: RESOLVED

Root cause (branch B): ClickHouse Operator did not refresh ready label after pod restart.
  - Pod label: clickhouse.altinity.com/ready=no
  - Service selector required: ready=yes
  - Result: Service endpoints = none → connection refused

Fix applied: kubectl rollout restart statefulset chi-<name> -n <ns>
  - Endpoints repopulated post-restart
  - External connectivity restored

Follow-up items:
  - [ ] Add alert: Service endpoints = none for > 2 min on stateful services
  - [ ] Add smoke test: post-restart endpoint readiness check in CI/deploy pipeline
  - [ ] Document operator label refresh behavior in runbook
```

---

## Pattern Cross-Reference

```
pattern_name:   connection-refused-layered-triage
related_cases:  case-mysql-connect-timeout-fp-dns-node (timeout variant)

key_principle:
  "refused = no listener; timeout = no route.
   Walk the chain A→H and stop at first failure.
   Never restart the database before checking endpoints and labels."

cluster_rule:
  "In Cluster 1, the first question is always:
   which hop in Client→DNS→LB→NodePort→ingress→svc→pod is broken?"
```
