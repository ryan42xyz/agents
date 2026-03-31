---
metadata:
  kind: runbook
  status: final
  summary: "End-to-end checklist for site access outages: start from the user side and DNS/connectivity, then narrow down to Kubernetes Pod/Service/Ingress, and extend to AWS ELB/security groups/route tables/Route 53/CloudFront and tracing to quickly isolate scope and find the root cause."
  tags: ["outage", "dns", "ingress", "aws", "networking"]
  first_action: "Run `dig` and `curl -v` to isolate DNS vs backend"
---

# Site Outage / Access Troubleshooting

## TL;DR (Do This First)
1. Scope: single user vs all users; single page vs whole site; specific ISP/network?
2. DNS: `dig +short <domain>`
3. Connectivity: `curl -v https://<domain>` and confirm status code / TLS
4. Backend chain: Service -> Ingress -> Pods (read-only snapshot)
5. If AWS edge is involved: ELB target health / SG / route / Route53

## Safety Boundaries
- Read-only: DNS/connectivity checks, `kubectl get/describe/logs`
- `#MANUAL`: changing DNS/Ingress/LB/security groups, restarting controllers

1. Cannot open a site - find the corresponding cluster - find the corresponding pod/service - check service status
    - The service is okay. And i can open on my side..  / Can you try with incognito mode?"

    - Can you ping it?
        - Yes
        - No
            - Does the service exist?
                - Service / Ingress, etc
                    - How this works is still not fully clear
                    - Especially after AWS was added
                - There may also be API gateways
                    - What services are on a given request path? How do I inspect it?
                    --- The surface is a DNS name; what is the underlying chain?
```
   # Test from inside a Kubernetes Pod
   kubectl --kubeconfig=/path/to/config -n default run dnsutils --rm -it --image=gcr.io/kubernetes-e2e-test-images/dnsutils:1.3 -- bash
   # Run diagnostics
   dig +short service.namespace.svc.cluster.local
   dig +short external-service.example.com
```

# Full Debugging Guide for Site Access Outages

## 1. Isolate the scope

### Initial checks
* **Client-side checks**:
  - Ask whether only a specific page fails or the whole site
  - Ask the user to try incognito mode / clear cache
  - Confirm whether it only happens on a specific device or network
  - Ask for a screenshot or an error code

### Basic network checks
* **DNS resolution**:
  ```bash
  dig +short <domain>
  nslookup <domain>
  ```
* **Connectivity tests**:
  ```bash
  ping <domain-or-ip>
  telnet <domain-or-ip> 80/443
  curl -v <site-url>
  ```

## 2. Server-side checks (Kubernetes)

### Identify the cluster and resources
* **List clusters**:
  ```bash
  kubectl config get-contexts
  # Or use a configured alias
  # kdev / kwest / keast etc
  ```

* **Locate relevant resources**:
  ```bash
  # Assume we know the relevant namespace and service name
  kubectl --kubeconfig=/path/to/config get ns
  kubectl --kubeconfig=/path/to/config -n <namespace> get pods,svc,ing
  ```

### Check Pod status
* **Confirm Pods are running**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> get pods
  kubectl --kubeconfig=/path/to/config -n <namespace> describe pod <pod-name>
  ```

* **Check Pod logs**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> logs <pod-name> -c <container-name> --tail=100
  # If the Pod restarted, check the previous container logs
  kubectl --kubeconfig=/path/to/config -n <namespace> logs <pod-name> -c <container-name> --previous
  ```

### Check Service and Ingress
* **Check Service**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> describe svc <service-name>
  # Confirm endpoints have healthy Pod IPs
  ```

* **Check Ingress**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> get ing
  kubectl --kubeconfig=/path/to/config -n <namespace> describe ing <ingress-name>
  ```

### Test from inside the cluster
* **Create a temporary debug Pod**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> run temp-debug --rm -i --tty --image=nicolaka/netshoot -- /bin/bash
  # After entering the Pod, run tests
  curl http://<service-name>:<port>
  ```

## 3. AWS checks

### Load balancer checks
* **Identify the related ALB/NLB/CLB**:
  ```bash
  # Find the ELB for the ingress-controller Service of type LoadBalancer
  kubectl --kubeconfig=/path/to/config -n <ingress-namespace> get svc

  # Query load balancers via AWS CLI
  aws elbv2 describe-load-balancers | grep <partial-elb-name>
  aws elbv2 describe-target-groups --load-balancer-arn <ALB-ARN>
  aws elbv2 describe-target-health --target-group-arn <Target-Group-ARN>
  ```

* **Check security group rules**:
  ```bash
  # Get security groups attached to the load balancer
  aws elbv2 describe-load-balancers --names <ALB-Name> --query 'LoadBalancers[0].SecurityGroups'

  # Check security group rules
  aws ec2 describe-security-groups --group-ids <Security-Group-ID>
  ```

### Network and routing checks
* **Check VPC and subnet configuration**:
  ```bash
  # View VPC and subnets
  aws ec2 describe-subnets --filters "Name=vpc-id,Values=<VPC-ID>"

  # Check route tables
  aws ec2 describe-route-tables --filters "Name=vpc-id,Values=<VPC-ID>"
  ```

* **Check ACLs and network policies**:
  ```bash
  aws ec2 describe-network-acls --filters "Name=vpc-id,Values=<VPC-ID>"
  ```

### Route 53 and CDN checks
* **Check DNS records**:
  ```bash
  aws route53 list-hosted-zones
  aws route53 list-resource-record-sets --hosted-zone-id <Zone-ID> | grep <domain-name>
  ```

* **If CloudFront is used**:
  ```bash
  aws cloudfront list-distributions | grep <domain-name>
  aws cloudfront get-distribution --id <Distribution-ID>
  ```

## 4. Deep-dive techniques

### Tracing
* Use **AWS X-Ray or compatible tools** to find issues in the service call chain
* Check service metrics and latency in **Prometheus/Grafana**
* Use **tcpdump or wireshark** to analyze network traffic

### Service mesh (e.g., Istio)
* **Check VirtualService and Gateway**:
  ```bash
  kubectl --kubeconfig=/path/to/config -n <namespace> get virtualservice,gateway
  kubectl --kubeconfig=/path/to/config -n <namespace> describe virtualservice <name>
  ```

* **Check service mesh health**:
  ```bash
  istioctl analyze -n <namespace>
  istioctl proxy-status
  ```

## 5. Map the end-to-end request path

### Full path from user to service
1. **User -> DNS resolution**
   - Route 53 (or another DNS provider) resolves the domain to the ELB endpoint

2. **DNS -> Load balancer**
   - ALB/NLB/CLB receives traffic
   - WAF/Shield (if configured) filters traffic

3. **Load balancer -> Kubernetes Ingress**
   - Traffic is forwarded to the Ingress Controller Pods
   - Ingress Controller routes traffic based on rules

4. **Ingress -> Service -> Pod**
   - Traffic is routed to the target Service
   - kube-proxy distributes traffic to Pods

5. **Application handles the request inside the Pod**
   - The app may call additional backend services

### How to inspect the full path
* Draw a network topology diagram to visualize traffic flow
* Use tracing tools like Jaeger to trace request paths
* Check API Gateway configuration if API Gateway is involved

## 6. Common issues and fixes

### Pods fail to start or restart frequently
* Check resource limits (CPU/memory)
* Check liveness/readiness probe configuration
* Check image version and configuration

### Network connectivity issues
* Check NetworkPolicy and other network policies
* Verify DNS resolution (CoreDNS)
* Check Service CIDR and Pod CIDR configuration

### Load balancer issues
* Health checks fail
* Backend instance/target registration issues
* Security group or ACL restrictions

### Security-related issues
* Certificate expired or misconfigured
* WAF rules incorrectly block requests
* CORS misconfiguration

## 7. Extend monitoring and alerting

* Set up **blackbox monitoring** to check availability regularly
* Configure **SLO/SLI** monitoring for key performance metrics
* Use **distributed tracing** to find service-to-service call issues
* Implement **synthetic monitoring** to simulate real user behavior

## 8. Prevent recurrence

* Maintain a detailed **operations runbook** documenting remediation steps
* Use **progressive delivery** and **automatic rollback** mechanisms
* Use **chaos engineering** to test resilience
* Run **post-incident analysis** and update monitoring and alerting
