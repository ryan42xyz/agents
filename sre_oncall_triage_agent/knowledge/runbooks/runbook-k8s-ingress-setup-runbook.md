---
metadata:
  kind: "runbook"
  status: "draft"
  tags: ["k8s", "ingress", "alb", "nginx", "route53", "aws"]
  first_action: "Verify the Deployment is healthy and the Service endpoints are correct."
  summary: "End-to-end Kubernetes Ingress configuration guide: from Deployment/Service to AWS Load Balancer Controller, Ingress rules and certificates, Route 53 DNS, verification and troubleshooting, with reusable YAML/CLI examples."
---

# Kubernetes Ingress Configuration Guide

This guide walks through configuring Ingress for a Kubernetes Deployment, including creating all required resources, from in-cluster configuration to AWS resources.

## Table of Contents
- [Kubernetes Ingress Configuration Guide](#kubernetes-ingress-configuration-guide)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Step 1: Verify the Deployment](#step-1-verify-the-deployment)
  - [Step 2: Create the Service](#step-2-create-the-service)
  - [Step 3: Confirm AWS Load Balancer Controller](#step-3-confirm-aws-load-balancer-controller)
  - [Step 4: Create the Ingress](#step-4-create-the-ingress)
  - [Step 5: Route 53 DNS configuration](#step-5-route-53-dns-configuration)
  - [Step 6: Verify the configuration](#step-6-verify-the-configuration)
  - [Troubleshooting](#troubleshooting)
  - [References](#references)

## Prerequisites

- A running Kubernetes cluster
- `kubectl` installed and configured with the correct cluster access
- AWS CLI installed and configured with valid credentials
- An AWS Certificate Manager (ACM) certificate (if HTTPS is required)
- A Route 53 hosted zone

## Step 1: Verify the Deployment

Confirm the current Deployment status:

```bash
# Check Deployment status
kubectl get deployment <deployment-name> -n <namespace>

# Confirm Pods are running normally
kubectl get pods -n <namespace> | grep <deployment-name>
```

## Step 2: Create the Service

1. Create a Service manifest file `service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <service-name>
  namespace: <namespace>
spec:
  selector:
    app: <deployment-label>  # must match the Pod labels in the Deployment
  ports:
    - protocol: TCP
      port: 80              # Service port
      targetPort: 8080      # container port
  type: ClusterIP          # use ClusterIP; expose via Ingress
```

2. Apply the Service manifest:

```bash
kubectl apply -f service.yaml
```

## Step 3: Confirm AWS Load Balancer Controller

1. Check controller status:

```bash
# Check whether AWS Load Balancer Controller is running
kubectl get deployment -n kube-system aws-load-balancer-controller

# Check whether IngressClass exists
kubectl get ingressclass
```

## Step 4: Create the Ingress

1. Create an Ingress manifest file `ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <ingress-name>
  namespace: <namespace>
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/actions.ssl-redirect: '{"Type": "redirect", "RedirectConfig": {"Protocol": "HTTPS", "Port": "443", "StatusCode": "HTTP_301"}}'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:region:account-id:certificate/certificate-id
    alb.ingress.kubernetes.io/security-groups: sg-xxx,sg-yyy
spec:
  rules:
    - host: your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: <service-name>
                port:
                  number: 80
```

2. Apply the Ingress manifest:

```bash
kubectl apply -f ingress.yaml
```

## Step 5: Route 53 DNS configuration

1. Get the ALB DNS name:

```bash
export ALB_DNS=$(kubectl get ingress <ingress-name> -n <namespace> -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo $ALB_DNS
```

2. Create the Route 53 record set:

```bash
# Get hosted zone ID
export ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name "your-domain.com." \
  --query "HostedZones[0].Id" --output text | sed 's/\/hostedzone\///')

# Create the JSON change-batch file
cat > route53-change.json << EOF
{
  "Comment": "Creating alias record for ALB",
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "your-domain.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "ZXXXXXXXXXX",  # ALB hosted zone ID
          "DNSName": "$ALB_DNS",
          "EvaluateTargetHealth": true
        }
      }
    }
  ]
}
EOF

# Apply DNS changes
aws route53 change-resource-record-sets \
  --hosted-zone-id $ZONE_ID \
  --change-batch file://route53-change.json
```

Notes:
- Replace `ZXXXXXXXXXX` with the actual ALB hosted zone ID (this is a fixed value per AWS region).
- Replace `your-domain.com` with the real domain name.
- If you need a subdomain, update the "Name" field (for example, `api.your-domain.com`).

## Step 6: Verify the configuration

1. Check resource status:

```bash
# Check Service status
kubectl get svc <service-name> -n <namespace>

# Check Ingress status
kubectl get ingress <ingress-name> -n <namespace>

# Check ALB status
aws elbv2 describe-load-balancers

# Check DNS propagation
dig your-domain.com
```

2. Test access:

```bash
# Test HTTP access
curl -v http://your-domain.com

# Test HTTPS access
curl -v https://your-domain.com
```

## Troubleshooting

If you hit issues, follow these steps:

1. Check Pod status:
```bash
kubectl get pods -n <namespace>
kubectl logs -f <pod-name> -n <namespace>
```

2. Check Service endpoints:
```bash
kubectl get endpoints <service-name> -n <namespace>
```

3. Check Ingress controller logs:
```bash
kubectl logs -n kube-system deployment.apps/aws-load-balancer-controller
```

4. Check ALB configuration:
```bash
# Check target group health
aws elbv2 describe-target-health --target-group-arn <target-group-arn>

# Check security group configuration
aws ec2 describe-security-groups --group-ids sg-xxx
```

5. Check DNS resolution:
```bash
# Check DNS records
aws route53 list-resource-record-sets --hosted-zone-id $ZONE_ID \
  --query "ResourceRecordSets[?Name == 'your-domain.com.']"

# Validate DNS resolution
dig +trace your-domain.com
```

Common issues:
1. ALB security group rules are incorrect
2. Target group health checks are failing
3. DNS record is not configured correctly
4. Certificate ARN is incorrect or the certificate is invalid
5. Pods are not ready or the Service port mapping is incorrect

## References

- [AWS Load Balancer Controller docs](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)
- [Kubernetes Ingress docs](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Route 53 Developer Guide](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/)
