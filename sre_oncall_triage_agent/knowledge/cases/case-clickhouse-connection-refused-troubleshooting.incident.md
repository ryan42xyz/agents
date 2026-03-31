---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-clickhouse-connection-refused-troubleshooting.md
  title: "ClickHouse External Connection Refused (NLB + ingress-nginx TCP)"
  summary: "ClickHouse `connection refused`: primary root cause — Pod restart left Operator not refreshing ready label, Service had no endpoints; layered triage (Client->DNS->LB->Ingress->Service/Endpoints->Pod) finds first broken hop; other branches: tcp-services not loaded, bind localhost only."
  tags: [clickhouse, kubernetes, ingress-nginx, nlb, networking, tcp]
  patterns: [connection-refused-layered-triage, clickhouse-bind-localhost, ingress-tcp-port-not-listening, service-endpoints-none]
  source_incident: "oncall_cognitive_control_plane/knowledge/blogs/oncall-clickhouse_canot_connect.md (2025-09-29)"
---

# Incident: ClickHouse External Connection Refused (NLB + ingress-nginx TCP)

## 1. Incident Overview
- Date: 2025-09-29 (example; align to actual)
- Severity: TBD
- Duration: TBD
- System: ClickHouse exposed via Service (and optionally AWS NLB -> NodePort -> ingress-nginx TCP)
- Impact: clients (e.g. Spring Boot / HikariPool) hit `connection refused` when connecting to ClickHouse Service DNS; `kubectl get endpoints` shows `ENDPOINTS <none>` for the ClickHouse Service(s).

## 2. System Context
- Architecture (relevant):
  - Entry: Client -> DNS -> AWS NLB -> NodePort -> ingress-nginx
  - Backend: Service -> Endpoints -> Pod -> ClickHouse process
- Key dependency: ingress-nginx TCP stream config (via `tcp-services` ConfigMap)
- Scale: TBD

## 3. Environment
- Cloud: AWS
- Platform: Kubernetes (distribution/version: TBD)
- Ingress: ingress-nginx (TCP/stream)
- Database: ClickHouse
- Storage: TBD

## 4. Trigger
- Trigger: external client errors show `connection refused` (vs `timeout`)
- Detection channel: TBD

## 5. Impact Analysis
- Blast radius: external access path; internal cluster connectivity may be normal depending on failing layer
- User-visible symptoms: connection refused
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: `get/describe/logs` and connectivity probes
- `#MANUAL`: restarting ingress/controller, changing ConfigMap/service ports, touching ClickHouse config/data nodes

## 7. Investigation Timeline
- Confirm error class: `refused` vs `timeout`.
- Walk the chain (A-H) and stop at the first broken layer:
  - DNS resolution
  - TCP connect to exposed port
  - Ingress runtime listening state (`ss -lntp` in controller pod)
  - Backend Service/Endpoints existence
  - Pod readiness/labels vs Service selector
- Process bind/listen (localhost vs pod IP)

## 8. Root Cause
- **Primary (fits “suddenly stopped working”)**: ClickHouse Pod had an abnormal restart (OOMKilled, node drain, crash, etc.). After restart, the **Altinity ClickHouse Operator did not refresh** the Pod label `clickhouse.altinity.com/ready` — it remained `no`. The Service selector requires `ready=yes`, so the Service had **no endpoints** (`kubectl get endpoints` showed `<none>`). Traffic to the Service DNS therefore hit nothing and clients saw `connection refused`. Before the restart, `ready=yes` was set and connectivity was normal; the regression was triggered by the restart + operator not updating the label.
- **Other branches** (choose by evidence; “always broken” if misconfigured from day one):
  - ingress-nginx did not actually listen on the TCP port because the controller did not load the `tcp-services` ConfigMap (external NLB path).
  - ClickHouse only listened on `127.0.0.1` and not on pod IP / `0.0.0.0` — would cause refusal for any external/pod-IP traffic from the start, not “one day suddenly.”

## 9. Mitigation
- **Resolution (primary branch)**: Restart the ClickHouse StatefulSet so the Operator re-evaluates and sets `clickhouse.altinity.com/ready=yes`; Service endpoints repopulate and clients can connect again. Example: `kubectl rollout restart statefulset chi-dv-datavisor-0-0 -n <namespace>`. Temporary workaround: use Pod DNS directly (e.g. `chi-dv-datavisor-0-0-0.<ns>.svc.cluster.local:8123`) to confirm ClickHouse is up.
- Other mitigation options (by branch):
  - If external access is intended: fix ClickHouse bind/listen host to include pod IP / `0.0.0.0`
  - If ClickHouse should be internal-only: remove external exposure and use ClusterIP
  - If ingress TCP is misconfigured: ensure controller references `tcp-services` and verify port is listening
  - If endpoints are missing: restore selector/label match (operator label refresh / controlled restart)

## 10. Prevention / Improvement
- Standardize refused/timeout decision tree (keep A-H chain in every runbook).
- Add automated checks:
  - controller args reference `tcp-services`
  - controller pod is listening on the intended TCP ports
  - Service endpoints are non-empty and match selectors
  - DB bind address matches intended exposure

## 11. Generalizable Lessons
- `refused` typically means "nothing is listening on that IP:port"; `timeout` points to routing/LB/network.
- LB health can be green while the application is unreachable (health checks may not cover backend).
- Always validate both:
  - spec/config ("should listen") and runtime ("is listening now").
- Pattern Card:
  - Pattern name: connection-refused-layered-triage
  - When it happens: external TCP entrypoint fails fast
  - Fast detection signals: `nc`/`telnet` refused; ingress `ss` missing port; endpoints `<none>`
  - Fast mitigation: fix bind/listen, refresh endpoints, fix ingress tcp-services wiring
  - Common pitfalls: restarting DB blindly; skipping endpoints/selector checks

## Tags & Patterns
- Tags: clickhouse, kubernetes, ingress-nginx, nlb, networking, tcp
- Patterns: connection-refused-layered-triage, clickhouse-bind-localhost, ingress-tcp-port-not-listening, service-endpoints-none
- First Action: confirm `refused` (not `timeout`), then walk hop by hop along Client -> DNS -> LB -> NodePort -> ingress -> svc -> pod

## Evidence Mapping
- Triage rule -> "Confirm the symptom is `refused` (not `timeout`) and record the failing endpoint/port" (case-clickhouse-connection-refused-troubleshooting.md:TL;DR (Do This First))
- Layer model -> "Walk the chain: Client -> DNS -> LB -> NodePort -> ingress-nginx -> Service/Endpoints -> Pod -> Process" (case-clickhouse-connection-refused-troubleshooting.md:TL;DR (Do This First))
- Key signal -> "refused != timeout; refused usually means nothing is listening on that IP:port" (case-clickhouse-connection-refused-troubleshooting.md:Chain Model)
- Key insight -> "Entry-layer health does not imply application reachability" (case-clickhouse-connection-refused-troubleshooting.md:One-line Essence)
- Root cause (primary, “suddenly stopped”) -> "Pod restart; Operator did not refresh ready label; Service selector requires ready=yes → ENDPOINTS <none> → connection refused" (oncall-clickhouse_canot_connect.md)
- Endpoints missing symptom -> "Service shows `ENDPOINTS <none>`" (case + oncall-clickhouse_canot_connect.md)
- Selector mismatch -> "Service selector required `clickhouse.altinity.com/ready=yes`; Pod label stayed ready=no after restart" (oncall-clickhouse_canot_connect.md)
- Alternative root cause -> "ClickHouse only listening on 127.0.0.1" (would imply always broken, not “suddenly”; case-clickhouse-connection-refused-troubleshooting.md)
