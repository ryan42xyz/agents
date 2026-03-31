---
metadata:
  kind: "checklist"
  status: "draft"
  tags: ["aws", "nlb", "alb", "k8s", "ingress-nginx", "troubleshooting"]
  first_action: "Check ingress controller pods and inspect recent controller logs."
  summary: "AWS LB + Ingress notes (DV oriented): organize the troubleshooting checklist by layered path (LB/Ingress/Service/Pod), focusing on common health check failures and routing issues; basic concepts are delegated to canonical external links."
---

# AWS LB + Ingress Notes (DV-Oriented)

This file removes generic ELB/Ingress 101 material and keeps what we actually use during troubleshooting: the layered path, key objects, and common pitfalls.

## External References (Canonical)

- Kubernetes Ingress: https://kubernetes.io/docs/concepts/services-networking/ingress/
- NGINX Ingress Controller: https://kubernetes.github.io/ingress-nginx/
- AWS Load Balancer Controller: https://kubernetes-sigs.github.io/aws-load-balancer-controller/
- NLB: https://docs.aws.amazon.com/elasticloadbalancing/latest/network/
- ALB: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/

## Layered Model

Client -> DNS -> AWS LB (NLB/ALB) -> Node/Ingress -> Service -> Pod

More detailed routing context: `./reference-request-routing-flow.md`

## Troubleshooting Checklist

### 1) Ingress controller health

```bash
kubectl -n ingress-nginx get pods -o wide
kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --tail 200
kubectl -n ingress-nginx describe deploy ingress-nginx-controller
```

### 2) Ingress + Service correctness

```bash
kubectl -n <ns> get ingress,svc
kubectl -n <ns> describe ingress <ing>
kubectl -n <ns> describe svc <svc>
kubectl -n <ns> get endpointslice -l kubernetes.io/service-name=<svc>
```

### 3) NLB/ALB health check failures

Common causes:

- health check port/path mismatch
- target group points to old nodes
- SG/NACL blocks health check traffic

Related oncall:

- `./runbook-site-outage-access-troubleshooting.md`
- `./runbook-nginx-debugging-runbook.md`

## Notes

- If you need "ELB types 101", use external references above.
- Add only DV-specific gotchas (a repeated incident, a non-obvious annotation dependency, a controller version pitfall).
