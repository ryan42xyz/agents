# loki_fetch

Directly queries Loki HTTP API — no Grafana MCP dependency.

**Loki**: `https://loki.dv-api.com` · `auth_enabled: true` · two tenants: `prod` and `nonprod`

---

## Quick start

```bash
# kwestdeva — dapp errors in last hour
LOKI_URL="https://loki.dv-api.com" LOKI_ORG_ID="nonprod" \
  python3 tools/loki_fetch/loki_fetch.py \
  --expr '{cluster="aws-uswest2-dev-a", app=~"dapp-.*"}' |= "ERROR"' \
  --from now-1h

# kwestproda — prod service errors
LOKI_URL="https://loki.dv-api.com" LOKI_ORG_ID="prod" \
  python3 tools/loki_fetch/loki_fetch.py \
  --expr '{cluster="aws-uswest2-prod-a", namespace="prod"} |= "ERROR"' \
  --from now-30m --limit 500
```

---

## Tenant → cluster mapping

### `LOKI_ORG_ID=nonprod`

| cluster label | kubectl alias |
|---|---|
| `aws-uswest2-dev-a` | `kwestdeva` |
| `aws-uswest2-dev-b` | `kwestdevb` |
| `aws-uswest2-preprod-a` | `kwestpreprod` |
| `aws-useast1-preprod-a` | — |
| `aws-useast1-pcipreprod-a` | — |
| `aws-afsouth1-preprod-a` | — |
| `aws-cacentral1-preprod-a` | — |
| `gcp-uswest1-prod-a` | — |

### `LOKI_ORG_ID=prod`

| cluster label | kubectl alias |
|---|---|
| `aws-uswest2-mgt-a` | `kwestmgt` |
| `aws-uswest2-prod-a` | `kwestproda` |
| `aws-uswest2-prod-b` | `kwestprodb` |
| `aws-uswest2-sandbox-a` | — |
| `aws-uswest2-sandbox-b` | — |
| `aws-useast1-prod-a` | — |
| `aws-useast1-prod-b` | — |
| `aws-useast1-pci-a` | — |
| `aws-useast1-pci-b` | — |
| `aws-cacentral1-prod-a/b` | — |
| `aws-euwest1-prod-a/b` | — |
| `aws-afsouth1-prod-a/b` | — |
| `aws-apsoutheast1-prod-a/b` | — |
| `aws-cawest1-prod-b` | — |
| `aws-euwest2-prod-b` | — |

**Rule of thumb**: dev/preprod/demo → `nonprod`; prod/mgt/sandbox → `prod`

---

## Usage

### Mode 1: Direct LogQL
```bash
python3 tools/loki_fetch/loki_fetch.py --expr '<LogQL>' [options]

# ISO8601 time range
python3 tools/loki_fetch/loki_fetch.py \
  --expr '{cluster="aws-uswest2-dev-a", app="dapp-server"} |= "ERROR"' \
  --from 2026-03-31T08:00:00Z --to 2026-03-31T09:00:00Z \
  --limit 500 --direction forward

# Check what apps exist in a cluster
python3 tools/loki_fetch/loki_fetch.py \
  --expr '{cluster="aws-uswest2-dev-a"}' --dry-run
```

### Mode 2: Parse Grafana Explore URL
```bash
python3 tools/loki_fetch/loki_fetch.py '<grafana_explore_url>'
```
Parses the `panes=` param and fetches directly without Grafana MCP.

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--expr` | — | LogQL expression |
| `--from` | `now-1h` | Start time: `now-Xh/m/s` or ISO8601 |
| `--to` | `now` | End time |
| `--limit` | 200 | Max log lines |
| `--direction` | `backward` | `backward` = newest first |
| `--loki-url` | `$LOKI_URL` | Loki base URL (required) |
| `--org-id` | `$LOKI_ORG_ID` or `fake` | `X-Scope-OrgID` tenant header |
| `--json` | off | Output NDJSON `{timestamp, labels, line}` |
| `--dry-run` | off | Print resolved params without fetching |

---

## Labels set by promtail

```
cluster:   <see table above>
namespace: <k8s namespace>
pod:       <pod name>
container: <container name>
app:       <pod label "app">
```

Known dapp apps in kwestdeva: `dapp-server`, `dapp-ui`, `dapp-mysql`

---

## Workflow in oncall agent

```
loki_fetch.py --expr <LogQL>
  OR
loki_fetch.py <grafana_explore_url>
  → stdout: "TIMESTAMP | log line"
  → agent saves to tmp/oncall_evidence/<label>/logs.log via Write tool
```

Query safety rules (from CLAUDE.md): every LogQL must include ≥1 stream selector; time window ≤ 6h; no `=~".*"` on high-cardinality labels (pod/container).
