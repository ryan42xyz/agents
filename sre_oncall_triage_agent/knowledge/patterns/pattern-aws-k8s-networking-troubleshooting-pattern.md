---
metadata:
  kind: "pattern"
  status: "draft"
  tags: ["aws", "k8s", "networking", "dns", "load-balancer", "troubleshooting"]
  first_action: "Classify the symptom as timeout vs connection refused, then map it to a layer."
  summary: "AWS/K8s networking notes (DV oriented): align Client->DNS->LB->Ingress->Service->Pod to a layered troubleshooting order; keep common failure patterns and executable commands; replace basic concept primers with canonical external docs."
---

# AWS/K8s Networking Notes (DV-Oriented)

This doc intentionally does not list the AWS/VPC/K8s networking basics that are easy to look up elsewhere (VPC/Subnet/RouteTable/SG/NACL/CNI, etc.).

Goal: keep what we actually use in our environment: path mapping, troubleshooting order, key differences, and executable commands.

## External References (Canonical)

- AWS VPC: https://docs.aws.amazon.com/vpc/
- Security Groups: https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html
- Network ACLs: https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html
- VPC Route Tables: https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html
- VPC Endpoints: https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html
- Kubernetes Networking: https://kubernetes.io/docs/concepts/cluster-administration/networking/

## Request Path (How We Think About It)

- High level: Client -> DNS -> AWS LB -> Node/Ingress -> Service -> Pod -> App
- More detailed routing context: `./reference-request-routing-flow.md`

## Common Failure Patterns

### 1) Connection refused vs timeout

- refused: likely one hop is not listening/forwarding or the port is not reachable (e.g., ingress tcp-services, svc targetPort, app not listening)
- timeout: likely blocked, missing route, or failing health checks (SG/NACL/Route/TargetGroup health check)
- Related oncall: `./case-clickhouse-connection-refused-troubleshooting.md`

### 2) LB health check fails

Checklist:

```bash
kubectl -n <ns> get svc,ingress
kubectl -n <ns> describe svc <svc>
kubectl -n <ns> describe ingress <ing>

kubectl -n ingress-nginx get pods -o wide
kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --tail 200

kubectl -n <ns> get endpointslice -l kubernetes.io/service-name=<svc>
kubectl -n <ns> get pod -o wide
```

### 3) DNS looks fine, but traffic still broken

Often:

- multi-cluster/multi-env: you resolved to the entry point of a different cluster
- LB target group points to old nodes / nodes are draining
- Route53 / DNS cache / client-side resolver not refreshed

## Troubleshooting Order (Layered)

### L0: Confirm symptom

```bash
dig +short <domain>
curl -vk --connect-timeout 3 --max-time 10 https://<domain>/health
```

### L1: AWS edge

- Confirm LB type (NLB/ALB) and listeners/target groups/health checks
- Confirm whether source is allowed (SG, NACL, IP allowlist, WAF if any)

### L2: Cluster entry (Ingress / Gateway)

- Check ingress controller pods are healthy
- Check controller logs show config sync success

### L3: Service routing

```bash
kubectl -n <ns> get svc <svc> -o yaml
kubectl -n <ns> get endpointslice -l kubernetes.io/service-name=<svc>
```

### L4: Pod/app

```bash
kubectl -n <ns> get pod -o wide
kubectl -n <ns> describe pod <pod>
kubectl -n <ns> logs <pod> --tail 200
kubectl -n <ns> exec -it <pod> -- ss -lntp
```

## CIDR Planning (Only What Matters)

- Ensure VPC CIDR does not overlap across environments that need connectivity.
- Standardize subnet sizes to avoid IP exhaustion surprises.

If you need the full textbook on CIDR/subnetting, use external references above.

## Notes

- This doc is intentionally short. If something becomes "DV-specific" (a real incident, a repeated pitfall, a non-obvious config dependency), add it here.
