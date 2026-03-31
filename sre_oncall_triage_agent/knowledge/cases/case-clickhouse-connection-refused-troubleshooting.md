---
metadata:
  kind: case
  status: final
  summary: "End-to-end layered troubleshooting for ClickHouse external `connection refused`: walk Client/DNS/AWS NLB/NodePort/ingress-nginx/Service/Pod/Process hop-by-hop to find where nothing is listening (common: tcp-services ConfigMap not loaded), reducing MTTR with structured signals."
  tags: ["clickhouse", "k8s", "ingress-nginx", "nlb", "networking"]
  first_action: "Confirm refused vs timeout first, then troubleshoot hop-by-hop along Client->DNS->LB->ingress->svc->pod"
  related:
    - ./case-clickhouse-connection-refused-troubleshooting.incident.md
    - ./checklist-aws-lb-ingress-troubleshooting-checklist.md
    - ./card-aws-k8s-network-triage-chain.md
    - ./card-nginx-fast-triage.md
    - ./card-dns-fast-triage.md
    - ./runbook-k8s-ingress-setup-runbook.md
    - ./runbook-dns-url-creation-runbook.md
    - ./card-site-outage-triage.md

---

# ClickHouse Connection Refused: End-to-End Troubleshooting

## TL;DR (Do This First)
1. Confirm the symptom is `refused` (not `timeout`), and record the failing endpoint/port
2. Walk hop-by-hop: Client -> DNS -> LB -> NodePort -> ingress-nginx -> Service/Endpoints -> Pod -> Process
3. If ingress is not listening on the TCP port, first verify whether the tcp-services ConfigMap is actually loaded by the controller (common root cause)

## Safety Boundaries
- Read-only: `get/describe/logs` and connectivity probes
- `#MANUAL`: restart ingress/controller, modify ConfigMap/service ports, any change to ClickHouse data nodes



## Related
- [case-clickhouse-connection-refused-troubleshooting.incident.md](./case-clickhouse-connection-refused-troubleshooting.incident.md)
- [checklist-aws-lb-ingress-troubleshooting-checklist.md](./checklist-aws-lb-ingress-troubleshooting-checklist.md)
- [card-aws-k8s-network-triage-chain.md](./card-aws-k8s-network-triage-chain.md)
- [card-nginx-fast-triage.md](./card-nginx-fast-triage.md)
- [card-dns-fast-triage.md](./card-dns-fast-triage.md)
- [card-site-outage-triage.md](./card-site-outage-triage.md)

## One-line Essence
`Connection refused` usually means "no process is listening" at that hop; walk Client -> DNS -> LB -> NodePort -> ingress -> Service -> Pod -> Process to prove where the listening breaks (common: ingress-nginx TCP not loaded / ClickHouse bound to `127.0.0.1` only).

## Triage
Stop at the first failing hop:

| Hop | Check | How (example) | Signal | Most likely next step |
| --- | --- | --- | --- | --- |
| 0 | Error classification | Record client error + timestamp | `refused` vs `timeout` | `refused`: check listeners first; `timeout`: check routing/LB/NodePort first |
| [A] Client | Pick a stable vantage point | Prefer testing from same VPC / from a pod inside the cluster | Results may differ by source | Re-test from a VPC EC2 or a debug pod |
| [B] DNS | Correct resolution | `nslookup` / `dig +short` | NXDOMAIN / wrong IP | Fix record / split-horizon |
| [C] AWS LB | LB reachable and targets healthy | `nc -vz <host> <port>`; check TG health | timeout / TG unhealthy | Fix NLB listener/TG/SG |
| [D] NodePort | NodePort reachable | Test `nodeIP:nodePort` | timeout / unreachable | Check SG/NACL/iptables; NodePort mapping |
| [E] ingress-nginx | Is the controller listening on the TCP port | In controller pod: `ss -lntp`; verify tcp-services wiring | `refused` + no listener | Fix/load tcp-services; restart controller if needed (`#MANUAL`) |
| [F] Service | svc/ports correct | `kubectl get svc` | wrong port/targetPort | Fix service spec |
| [G] Endpoints | Has Ready endpoints | `kubectl get endpoints` | `<none>` | Check selector/labels/readiness gating |
| [H] Process | ClickHouse bound to Pod IP | In CH pod: `ss -lntp`; compare `localhost` vs PodIP | only listens on `127.0.0.1` | Adjust ClickHouse bind/listen (`#MANUAL`) |

Decision rules worth keeping:
- If `kubectl get endpoints <svc>` shows `<none>`, first check the Service selector and pod labels (operator-managed ClickHouse often uses labels like `clickhouse.altinity.com/ready=yes` for endpoints gating).
- If ingress-nginx is not listening on the TCP port, verify tcp-services is configured and actually referenced/loaded by the controller (a ConfigMap existing but not loaded looks like "no listener").
- If the backend only listens on `127.0.0.1`, external traffic will still see `refused` even if NLB/TG/NodePort look healthy; fix by binding/listening on `0.0.0.0`/Pod IP (`#MANUAL`).

## Verification
- External probe succeeds (`nc`/`telnet`) and hits the expected endpoint/port
- ingress-nginx is actually listening on the TCP port (controller `ss -lntp`)
- Service Endpoints are non-empty and backend pods are Ready
- ClickHouse listens on `0.0.0.0`/PodIP (not only `127.0.0.1`)

## Closeout
- Record: failing hop ([A]-[H]), error type (`refused`/`timeout`), and the output that proves it
- If any `#MANUAL` change happened (ConfigMap/rollout/restart), record who/when/what and include the change link
- Add prevention items: guardrails for tcp-services/controller args + a minimal end-to-end smoke test

## Quick Commands (Optional)

```bash
# Client-side: distinguish refused vs timeout
nc -vz <host> <port>

# DNS
nslookup <host>
dig +short <host>

# ingress-nginx: is the TCP port actually listening?
kubectl -n ingress-nginx exec -it <controller-pod> -- ss -lntp

# ingress-nginx TCP mapping
kubectl -n ingress-nginx get cm tcp-services -oyaml
kubectl -n ingress-nginx get deploy ingress-nginx-controller -oyaml | grep -n "tcp-services"

# Backend plumbing
kubectl -n <ns> get svc <svc> -o wide
kubectl -n <ns> get endpoints <svc> -o wide

# Backend process: does ClickHouse listen beyond localhost?
kubectl -n <ns> exec -it <clickhouse-pod> -- ss -lntp
```
