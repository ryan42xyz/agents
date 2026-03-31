# loki_fetch

Directly queries Loki HTTP API — no Grafana MCP dependency.

## Usage

### Mode 1: Grafana Explore URL
```bash
python3 ./tools/loki_fetch/loki_fetch.py '<grafana_explore_url>'
```

### Mode 2: Direct LogQL
```bash
python3 ./tools/loki_fetch/loki_fetch.py --expr '{cluster="aws-uswest2-dev", app="dapp"}' --from now-1h

# With explicit time range
python3 ./tools/loki_fetch/loki_fetch.py \
  --expr '{cluster="aws-uswest2-dev", namespace="default"} |= "ERROR"' \
  --from 2026-03-31T08:00:00Z --to 2026-03-31T09:00:00Z \
  --limit 500

# Dry-run: see resolved params without fetching
python3 ./tools/loki_fetch/loki_fetch.py --expr '{app="dapp"}' --dry-run
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--expr` | — | LogQL expression |
| `--from` | `now-1h` | Start time (`now-Xh/m/s` or ISO8601) |
| `--to` | `now` | End time |
| `--limit` | 200 | Max lines |
| `--direction` | `backward` | `backward` = newest first, `forward` = oldest first |
| `--loki-url` | `$LOKI_URL` or `https://loki.example.com` | Loki endpoint |
| `--org-id` | `$LOKI_ORG_ID` or `fake` | `X-Scope-OrgID` header |
| `--json` | off | Output NDJSON (timestamp + labels + line) |
| `--dry-run` | off | Print resolved query params, no fetch |

## Environment

```bash
export LOKI_URL="https://loki.example.com"
export LOKI_ORG_ID="fake"   # override per-cluster if multi-tenant
```

## Label reference (kwestdeva)

Promtail config for dev us-west-2 sets:
```
cluster: aws-uswest2-dev
namespace: <k8s namespace>
pod: <pod name>
container: <container name>
app: <pod label app>
```

Typical oncall queries:
```logql
# dapp deploy logs (last 1h)
{cluster="aws-uswest2-dev", app="dapp"}

# errors only
{cluster="aws-uswest2-dev", namespace="default"} |= "ERROR" | logfmt

# specific pod
{cluster="aws-uswest2-dev", pod=~"dapp-.*"}
```

## Workflow

```
loki_fetch.py --expr <LogQL>         # Mode 1: direct query
  OR
loki_fetch.py <grafana_explore_url>  # Mode 2: parse URL → query

  → stdout: formatted log lines
  → agent saves to tmp/oncall_evidence/<label>/logs.log via Write tool
```

## Notes

- **No Grafana MCP required** — calls Loki `/loki/api/v1/query_range` directly
- Read-only; all queries are logged by `mcp-audit.sh` (Bash tool hook)
- If `X-Scope-OrgID` is wrong for your cluster, set `LOKI_ORG_ID` or `--org-id`
