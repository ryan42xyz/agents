---
metadata:
  kind: reference
  status: draft
  summary: "Card: AWS+K8s DNS quick triage (CoreDNS vs Route53), including minimal checks and isolation steps."
  tags: ["card", "dns", "coredns", "aws", "route53", "k8s", "oncall"]
  first_action: "First decide: in-cluster DNS (CoreDNS) or external DNS (Route53)"
---

# Card: DNS Quick Triage (CoreDNS vs Route53)

## TL;DR (Do This First)
1. Confirm: which domain is failing, and where it fails (client / pod / node)?
2. Decide the layer: CoreDNS (in-cluster) or Route53 (AWS)
3. Compare a known-good vantage point against the failing one

## Minimal Checks
```bash
dig +short <host>
nslookup <host>

# In cluster (debug pod if available)
kubectl run dns-test --rm -it --image=busybox:1.36 --restart=Never -- nslookup kubernetes.default
```

## Signals
- Resolves externally but fails inside pods: CoreDNS / node DNS / network policy.
- Fails only on some pods/nodes: node-level DNS/egress issue.
- Resolves to an unexpected IP: split-horizon or record misconfiguration.

## Further Reading (Deep Doc)
- Full reference: [reference-dns-configuration-reference.md](./reference-dns-configuration-reference.md)
