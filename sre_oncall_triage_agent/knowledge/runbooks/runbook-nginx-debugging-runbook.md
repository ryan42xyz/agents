---
metadata:
  kind: runbook
  status: final
  summary: "Nginx debugging and management command checklist: covers status/port checks under systemd, error/system log triage, start/stop/restart/reload workflows, and a standardized path from symptom to root cause for day-to-day ops and oncall incident handling."
  tags: ["nginx", "ingress", "k8s", "troubleshooting"]
  first_action: "Run `systemctl status nginx` and `nginx -t`"
---

# Nginx Debugging and Management Command Checklist

## TL;DR (Do This First)
1. Confirm service status: `systemctl status nginx`
2. Validate config syntax: `nginx -t`
3. Check recent errors: `journalctl -u nginx --since "1 hour ago"` and error log
4. Only after you have evidence, do `#MANUAL` restart/reload

## Safety Boundaries
- Read-only: status/logs/config test
- `#MANUAL`: `systemctl restart nginx`, `nginx -s reload` (risk: traffic impact)

## Overview

This document provides a standardized nginx debugging and management command checklist for systemd-based Linux systems (such as Ubuntu, Debian, and CentOS 7+).

Contents:
- **Status checks**: service state and listening ports
- **Log checks**: error logs and system logs
- **Service control**: start, stop, restart, reload
- **Debug workflow**: a systematic path to isolate issues

---

## 1. Check Nginx status

### 1. Current service status

```bash
systemctl status nginx
```

**Purpose**: check whether nginx is running, its PID, and recent log lines.

**Status meanings**:
- `active (running)` -> running normally
- `inactive (dead)` -> not running
- `failed` -> failed to start

**Example output**:
```
● nginx.service - A high performance web server and a reverse proxy server
     Loaded: loaded (/lib/systemd/system/nginx.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2025-11-24 10:30:45 UTC; 2h 15min ago
       Docs: man:nginx(8)
    Process: 1234 ExecStartPre=/usr/sbin/nginx -t -q -g daemon on; master_process on; (code=exited, status=0/SUCCESS)
    Process: 1235 ExecStart=/usr/sbin/nginx -g daemon on; master_process on; (code=exited, status=0/SUCCESS)
   Main PID: 1236 (nginx)
      Tasks: 9 (limit: 4915)
     Memory: 15.2M
     CGroup: /system.slice/nginx.service
             ├─1236 nginx: master process /usr/sbin/nginx -g daemon on; master_process on;
             ├─1237 nginx: worker process
             └─1238 nginx: worker process
```

---

### 2. Check listening ports

```bash
sudo ss -tulnp | grep nginx
```

**Or use netstat**:
```bash
sudo netstat -tulnp | grep nginx
```

**Purpose**: confirm nginx is listening on port 80 and/or 443.

**Example output**:
```
tcp   LISTEN 0      511          0.0.0.0:80        0.0.0.0:*    users:(("nginx",pid=1236,fd=6))
tcp   LISTEN 0      511          0.0.0.0:443       0.0.0.0:*    users:(("nginx",pid=1236,fd=7))
tcp   LISTEN 0      511             [::]:80           [::]:*    users:(("nginx",pid=1236,fd=8))
tcp   LISTEN 0      511             [::]:443          [::]:*    users:(("nginx",pid=1236,fd=9))
```

**Key fields**:
- `0.0.0.0:80` -> listening on all IPv4 interfaces for port 80
- `[::]:80` -> listening on all IPv6 interfaces for port 80
- `pid=1236` -> nginx master process PID

---

### 3. Check processes

```bash
ps -ef | grep nginx
```

**Expected output**: you should see one master and multiple worker processes.

**Example output**:
```
root      1236     1  0 10:30 ?        00:00:00 nginx: master process /usr/sbin/nginx -g daemon on; master_process on;
www-data  1237  1236  0 10:30 ?        00:00:05 nginx: worker process
www-data  1238  1236  0 10:30 ?        00:00:05 nginx: worker process
www-data  1239  1236  0 10:30 ?        00:00:05 nginx: worker process
www-data  1240  1236  0 10:30 ?        00:00:05 nginx: worker process
```

**Process notes**:
- **master process** (root user): the master process, manages worker processes
- **worker process** (www-data user): workers that handle requests
- Worker count is often equal to CPU core count

---

## 2. Check logs

### 1. Nginx error log

```bash
tail -n 50 /var/log/nginx/error.log
```

**Or follow continuously**:
```bash
tail -f /var/log/nginx/error.log
```

**Errors to focus on**:
- `bind() failed` -> port is already in use
- `invalid directive` -> configuration error
- `permission denied` -> permission issue
- `upstream timed out` -> backend service timeout
- `could not build server_names_hash` -> server_names_hash_bucket_size is too small

**Common error example**:
```
2025/11/24 10:30:45 [emerg] 1234#1234: bind() to 0.0.0.0:80 failed (98: Address already in use)
2025/11/24 10:30:45 [emerg] 1234#1234: still could not bind()
```

---

### 2. Systemd logs

```bash
journalctl -xeu nginx
```

**Or stream logs**:
```bash
journalctl -fu nginx
```

**Purpose**: these are system-level logs that include start/stop actions and why the PID exited.

**Example output**:
```
Nov 24 10:30:45 server systemd[1]: Starting A high performance web server and a reverse proxy server...
Nov 24 10:30:45 server nginx[1234]: nginx: configuration file /etc/nginx/nginx.conf test is successful
Nov 24 10:30:45 server systemd[1]: Started A high performance web server and a reverse proxy server.
```

**Common journalctl options**:
- `-xe` -> show recent logs and explain errors
- `-f` -> follow logs
- `-u nginx` -> only nginx unit logs
- `-n 100` -> last 100 lines
- `--since "10 minutes ago"` -> last 10 minutes

---

### 3. Access log

```bash
tail -f /var/log/nginx/access.log
```

**Example format**:
```
192.168.1.100 - - [24/Nov/2025:10:30:45 +0000] "GET /api/v1/health HTTP/1.1" 200 15 "-" "curl/7.68.0"
192.168.1.101 - - [24/Nov/2025:10:30:46 +0000] "POST /api/v1/login HTTP/1.1" 401 56 "-" "Mozilla/5.0"
```

**Fields**:
- `192.168.1.100` -> client IP
- `GET /api/v1/health` -> HTTP method and path
- `200` -> HTTP status code
- `15` -> response size (bytes)

---

## 3. Control the nginx service

### 1. Start

```bash
sudo systemctl start nginx
```

---

### 2. Stop

```bash
sudo systemctl stop nginx
```

**Graceful stop (wait for in-flight requests)**:
```bash
sudo nginx -s quit
```

**Immediate stop (drops current connections)**:
```bash
sudo nginx -s stop
```

---

### 3. Restart

```bash
sudo systemctl restart nginx
```

**Note**: this fully stops and starts nginx and may cause a brief interruption.

---

### 4. Reload config (no interruption)

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Notes**:
- `nginx -t` -> test config syntax first
- `&&` -> reload only if the test succeeds
- `reload` -> graceful reload without interrupting service

**Recommendation**: always test first, then reload, to avoid outages caused by bad config.

**Separate commands**:
```bash
# 1. Test config
sudo nginx -t

# 2. If test succeeds, reload config
sudo systemctl reload nginx
```

---

### 5. Clear "start-limit-hit" lockout

If nginx fails to start repeatedly in a short period, systemd enters a protective state:

```
Failed to start nginx.service: Start request repeated too quickly.
```

**Fix**:
```bash
# Reset failed state
sudo systemctl reset-failed nginx

# Then restart
sudo systemctl start nginx
```

---

### 6. Enable start on boot

```bash
# Enable on-boot startup
sudo systemctl enable nginx

# Disable on-boot startup
sudo systemctl disable nginx

# Check whether it is enabled
systemctl is-enabled nginx
```

---

## 4. Common debug workflow

### 1. Config syntax check

```bash
sudo nginx -t
```

**Success output**:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

**Failure output example**:
```
nginx: [emerg] invalid directive "server_nam" in /etc/nginx/conf.d/default.conf:5
nginx: configuration file /etc/nginx/nginx.conf test failed
```

---

### 2. Print the full expanded config (including include)

```bash
sudo nginx -T | less
```

**Purpose**:
- View the merged config after all includes
- Useful for quickly searching keywords like `listen`, `server_name`, and `pid`

**Search examples**:
```bash
# Search for all listen directives
sudo nginx -T | grep listen

# Search for a specific server_name
sudo nginx -T | grep "server_name api.example.com"
```

---

### 3. Check config include paths

```bash
grep include /etc/nginx/nginx.conf
```

**Confirm the included directories have valid files**:
```bash
ls /etc/nginx/conf.d/
ls /etc/nginx/sites-enabled/
```

**Typical config layout**:
```
/etc/nginx/
├── nginx.conf              # main config file
├── conf.d/                 # custom config directory
│   ├── default.conf
│   └── api.conf
├── sites-available/        # available site configs
│   ├── default
│   └── myapp.conf
└── sites-enabled/          # enabled site configs (symlinks)
    ├── default -> ../sites-available/default
    └── myapp.conf -> ../sites-available/myapp.conf
```

---

### 4. Check daemon mode

```bash
grep daemon /etc/nginx/nginx.conf
```

**Notes**:
- Under systemd, you **do not need** `daemon off;`
- If `daemon off;` exists, remove it or comment it out

**Correct config**:
```nginx
# Not needed when managed by systemd
# daemon off;
```

---

### 5. Check PID file path consistency

```bash
# Check PID path in nginx.conf
grep pid /etc/nginx/nginx.conf

# Check PID path in systemd service file
grep PIDFile /lib/systemd/system/nginx.service
```

**Note**: these should match (commonly `/var/run/nginx.pid` or `/run/nginx.pid`).

**Example**:
```nginx
# /etc/nginx/nginx.conf
pid /var/run/nginx.pid;
```

```ini
# /lib/systemd/system/nginx.service
[Service]
PIDFile=/var/run/nginx.pid
```

---

### 6. Check port conflicts

```bash
sudo ss -tulnp | grep ':80\|:443'
```

**Or**:
```bash
sudo lsof -i :80
sudo lsof -i :443
```

**If the port is occupied**:
- Option 1: stop the process using the port
- Option 2: change nginx to use a different port
- Option 3: change the other service's port configuration

**Find the process holding the port**:
```bash
sudo lsof -i :80
```

**Example output**:
```
COMMAND   PID     USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
apache2  1234     root    4u  IPv6  12345      0t0  TCP *:http (LISTEN)
```

**Fix**:
```bash
# Stop Apache
sudo systemctl stop apache2
sudo systemctl disable apache2

# Then start nginx
sudo systemctl start nginx
```

---

### 7. Check file permissions

```bash
# Check config file permissions
ls -l /etc/nginx/nginx.conf
ls -l /etc/nginx/conf.d/

# Check log directory permissions
ls -ld /var/log/nginx/

# Check site root directory permissions
ls -ld /var/www/html/
```

**Common permission issues**:
- nginx config should be root:root with mode 644
- log directory should be www-data:adm with mode 755
- site files should be www-data:www-data or root:root and readable

**Example fixes**:
```bash
# Fix config file permissions
sudo chown root:root /etc/nginx/nginx.conf
sudo chmod 644 /etc/nginx/nginx.conf

# Fix log directory permissions
sudo chown -R www-data:adm /var/log/nginx/
sudo chmod 755 /var/log/nginx/

# Fix site directory permissions
sudo chown -R www-data:www-data /var/www/html/
sudo chmod -R 755 /var/www/html/
```

---

### 8. Check SELinux (CentOS/RHEL)

```bash
# Check SELinux status
getenforce

# View SELinux denial logs
sudo ausearch -m avc -ts recent | grep nginx

# Temporarily disable SELinux (for testing only)
sudo setenforce 0

# Permanently disable SELinux (not recommended; configure properly)
# Edit /etc/selinux/config, set SELINUX=permissive
```

---

## 5. Minimal recovery approach

If you cannot pinpoint the issue quickly, test with a minimal config:

```bash
# Create minimal test config
echo 'server { listen 80 default_server; return 200 "ok\n"; }' | sudo tee /etc/nginx/conf.d/test.conf

# Test and restart
sudo nginx -t && sudo systemctl restart nginx

# Test access
curl http://localhost
```

**Note**: if this works, the original configuration is likely the problem.

**Recovery steps**:
1. Back up the current configuration
2. Restore the original configuration files step by step
3. After each restore, test: `nginx -t`
4. Identify the config file that causes the issue

---

## 6. Common issues

### Issue 1: nginx cannot start

**Steps**:
1. Check config syntax: `sudo nginx -t`
2. Check error logs: `tail -f /var/log/nginx/error.log`
3. Check system logs: `journalctl -xeu nginx`
4. Check port conflicts: `sudo ss -tulnp | grep :80`
5. Check file permissions
6. Reset failed state: `sudo systemctl reset-failed nginx`

---

### Issue 2: config changes do not take effect

**Steps**:
1. Confirm config syntax is valid: `sudo nginx -t`
2. Use reload instead of restart: `sudo systemctl reload nginx`
3. Check for overriding configs: `sudo nginx -T | grep <directive>`
4. Clear browser cache
5. Check reverse proxy caches

---

### Issue 3: 502 Bad Gateway

**Common causes**:
- Backend service is not running
- Backend service is listening on the wrong address
- Firewall blocks the connection
- Upstream timeout is set too low

**Commands**:
```bash
# Check backend service is running
systemctl status <backend-service>

# Check backend service listening port
ss -tulnp | grep <backend-port>

# Test connecting to backend service
curl http://localhost:<backend-port>

# View nginx upstream errors
tail -f /var/log/nginx/error.log | grep upstream
```

---

### Issue 4: 504 Gateway Timeout

**Common causes**:
- Backend processing time is too long
- Upstream timeout is set too low
- Network latency

**Fix**:
```nginx
# Increase timeouts in nginx config
location /api {
    proxy_pass http://backend;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
}
```

---

### Issue 5: SSL certificate issues

**Commands**:
```bash
# Check certificate file exists
ls -l /etc/nginx/ssl/

# Check certificate expiry
openssl x509 -in /etc/nginx/ssl/cert.pem -noout -dates

# Check certificate and private key match
openssl x509 -noout -modulus -in /etc/nginx/ssl/cert.pem | openssl md5
openssl rsa -noout -modulus -in /etc/nginx/ssl/key.pem | openssl md5

# Test SSL config
openssl s_client -connect localhost:443 -servername example.com
```

---

## 7. Debug priority order

Following this order helps you pinpoint most issues quickly:

1. **Syntax validation**: `nginx -t`
2. **Error log**: `tail -f /var/log/nginx/error.log`
3. **Listening ports**: `ss -tulnp | grep nginx`
4. **PID file matches systemd**
5. **Config logic is correct** (at least one server block is listening)
6. **Daemon mode is correct** (systemd does not need daemon off)
7. **Restart after clearing failed state**: `systemctl reset-failed nginx`
8. **File permissions**: check permissions for config files, log directories, and site roots
9. **SELinux/AppArmor**: check whether the security module blocks nginx

---

## 8. Useful config snippets

### 1. Basic template

```nginx
user www-data;
worker_processes auto;
pid /run/nginx.pid;
error_log /var/log/nginx/error.log;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    keepalive_timeout 65;

    include /etc/nginx/conf.d/*.conf;
}
```

---

### 2. Reverse proxy

```nginx
upstream backend {
    server 127.0.0.1:8080;
    server 127.0.0.1:8081 backup;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

---

### 3. SSL/TLS

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # modern SSL config
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    location / {
        root /var/www/html;
        index index.html;
    }
}

# HTTP redirect to HTTPS
server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 9. Performance tuning tips

### 1. Worker tuning

```nginx
# Auto-set to number of CPU cores
worker_processes auto;

# Pin workers to CPU cores
worker_cpu_affinity auto;

# Increase connections per worker
events {
    worker_connections 4096;
}
```

---

### 2. Buffer tuning

```nginx
http {
    # increase buffer sizes
    client_body_buffer_size 128k;
    client_max_body_size 10m;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 4k;
    output_buffers 1 32k;
    postpone_output 1460;
}
```

---

### 3. Caching

```nginx
http {
    # proxy caching
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m max_size=1g inactive=60m;

    server {
        location / {
            proxy_pass http://backend;
            proxy_cache my_cache;
            proxy_cache_valid 200 60m;
            proxy_cache_valid 404 1m;
            add_header X-Cache-Status $upstream_cache_status;
        }
    }
}
```

---

## 10. Related docs

- [System architecture: request routing flow](./reference-request-routing-flow.md)
- [Kubernetes networking troubleshooting pattern](./pattern-aws-k8s-networking-troubleshooting-pattern.md)
- [Ingress setup guide](./runbook-k8s-ingress-setup-runbook.md)
- [Load balancer port configuration (ingress-nginx TCP)](./runbook-ingress-nginx-tcp-services-nlb-port-config.md)

---

## Changelog

- **2025-11-24**: initial version, includes the full nginx debugging and management flow
- Add common issue triage and fixes
- Add config templates and performance tuning suggestions

---

## Contact and support

If you have questions or suggestions:
1. Read nginx official docs: https://nginx.org/en/docs/
2. Check error logs: `/var/log/nginx/error.log`
3. Contact the oncall team





