---
metadata:
  kind: runbook
  status: draft
  summary: "Card: Nginx/ingress-nginx 5-minute quick triage: status, config validation, listen ports, error logs, and the safest reload/restart boundaries."
  tags: ["card", "nginx", "ingress", "k8s", "troubleshooting", "oncall"]
  first_action: "First confirm: host systemd nginx or the ingress-nginx controller"
---

# Card: Nginx 5-Minute Quick Triage

## TL;DR (Do This First)
1. First confirm which Nginx you are debugging: host nginx (systemd) or the `ingress-nginx` controller
2. Confirm the process is running and listening on the expected ports
3. Run config validation (`nginx -t`) and inspect error logs around the failure time
4. Prefer reload over restart; any change/restart is `#MANUAL`

## If This Is Host Nginx (systemd)
```bash
sudo systemctl status nginx
sudo nginx -t
sudo ss -lntp | grep nginx || true

# logs (pick what exists)
sudo journalctl -u nginx --since "10 min ago" | tail -n 200
sudo tail -n 200 /var/log/nginx/error.log
```

Manual actions:
```bash
#MANUAL
sudo systemctl reload nginx
sudo systemctl restart nginx
```

## If This Is ingress-nginx (Kubernetes)
```bash
kubectl get pod -n ingress-nginx -o wide
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller --tail=200

# Is it listening on the expected ports?
kubectl exec -n ingress-nginx deploy/ingress-nginx-controller -- ss -lntp

# If you use tcp-services / udp-services, verify the ConfigMap exists and is referenced by controller args
kubectl get cm -n ingress-nginx
kubectl get deploy -n ingress-nginx ingress-nginx-controller -o yaml | sed -n '1,200p'
```

Manual actions:
```bash
#MANUAL
kubectl rollout restart -n ingress-nginx deploy/ingress-nginx-controller
kubectl rollout status -n ingress-nginx deploy/ingress-nginx-controller
```

## Evidence To Capture (Do Not Paste Everything)
- Failing endpoint/port + error type (timeout vs refused)
- Listening proof (relevant `ss -lntp` lines)
- `nginx -t` output (1-3 lines)
- 20-50 log lines around the failure timestamp

## Further Reading (Deep Doc)
- Full runbook: [runbook-nginx-debugging-runbook.md](./runbook-nginx-debugging-runbook.md)
