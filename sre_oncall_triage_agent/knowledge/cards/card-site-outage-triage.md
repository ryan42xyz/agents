---
metadata:
  kind: runbook
  status: draft
  summary: "Card: Site outage quick triage (DNS->TCP->Ingress->Service->Pod) to quickly isolate the first break point in user access failures."
  tags: ["card", "outage", "dns", "ingress", "aws", "networking", "oncall"]
  first_action: "Use dig + curl first to isolate DNS vs backend"
---

# Card: Site Outage - Quick Triage

## TL;DR (Do This First)
1. Run `dig` and `curl -v` from a stable vantage point (ideally same region)
2. DNS wrong: fix records/TTL/routing path
3. DNS OK: check TCP reachability and LB/Ingress health
4. Ingress OK: check Service/Endpoints/Pod readiness

## Minimal Commands
```bash
dig +short <host>
curl -v --max-time 3 https://<host>/health || true
nc -vz <host> 443

kubectl get ingress -A | grep -i <name>
kubectl get svc -A | grep -i <name>
kubectl get endpoints -A | grep -i <name>
```

## Further Reading (Deep Doc)
- Full runbook: [runbook-site-outage-access-troubleshooting.md](./runbook-site-outage-access-troubleshooting.md)
