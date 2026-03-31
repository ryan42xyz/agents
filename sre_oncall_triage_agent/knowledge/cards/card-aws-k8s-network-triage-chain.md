---
metadata:
  kind: pattern
  status: draft
  summary: "Card: AWS/K8s network troubleshooting chain (Client->DNS->LB->NodePort->Ingress->Service->Pod->Process), including an attribution map for timeout vs refused and a minimal command set."
  tags: ["card", "aws", "k8s", "networking", "dns", "ingress", "oncall"]
  first_action: "First classify the error: timeout vs refused"
---

# Card: AWS/K8s Network Troubleshooting Chain

## TL;DR (Do This First)
1. First classify: `timeout` vs `refused`
2. Pick a stable vantage point (same VPC / debug pod) and run a TCP probe
3. Walk the chain hop-by-hop; stop at the first failing point

## Error Class -> Likely Layer
- `refused`: the chain reaches the hop, but that hop is *not listening* / not accepting (ingress not listening, svc endpoints empty, process only binds localhost)
- `timeout`: more likely routing/firewall/health check/target selection (SG/NACL/routes/TG health)

## Chain (Stop At First Failure)
`Client -> DNS -> AWS LB -> NodePort -> Ingress -> Service -> Endpoints -> Pod -> Process`

## Minimal Commands
```bash
# DNS
dig +short <host>
nslookup <host>

# TCP
nc -vz <host> <port>

# K8s
kubectl get svc -A | grep -i <name>
kubectl get endpoints -n <ns> <svc> -o wide
kubectl get pod -n <ns> -o wide
```

## Common Oncall Patterns
- LB healthy but app unavailable: the health check does not cover the real backend listen point.
- Service `ENDPOINTS <none>`: selector/label/readiness gating issue, not networking.
- Works in-cluster but not externally: usually ingress/LB wiring or process bind address.

## Further Reading (Deep Doc)
- Full pattern: [pattern-aws-k8s-networking-troubleshooting-pattern.md](./pattern-aws-k8s-networking-troubleshooting-pattern.md)
