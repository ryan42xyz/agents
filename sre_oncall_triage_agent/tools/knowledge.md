```sh
# victoriametrics usage:
# codex mcp


# grafana usage:
# export GRAFANA_URL='https://grafana.example.com'
# export GRAFANA_USERNAME='user@example.com'
# export GRAFANA_PASSWORD='${GRAFANA_PASSWORD}'  # provide via env/secret store; do not hardcode
# curl -fsS -u "$GRAFANA_USERNAME:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/health"

# loki usage:
# LOKI_URL="https://loki.example.com" && NOW=$(date +%s)000000000 && HOUR_AGO=$(($(date +%s) - 3600))000000000 && echo "=== Query logs containing 'error' ===" && curl -s -G "${LOKI_URL}/loki/api/v1/query_range" --data-urlencode "query={app=\"my-app\"} |= \"error\"" --data-urlencode "start=${HOUR_AGO}" --data-urlencode "end=${NOW}" --data-urlencode "limit=5" --data-urlencode "direction=backward" | jq '.data.result'

# LOKI_URL="https://loki.example.com"  # provide via env/secret store; do not hardcode

# END_NS="$(date +%s)000000000"
# START_NS="$(($(date +%s) - 1800))000000000"   # now-30m

# QUERY='{cluster="CLUSTER",namespace="NAMESPACE",pod=~".*",stream=~"stdout|stderr",container="CONTAINER"} |~ ""'

# curl -s -G "${LOKI_URL}/loki/api/v1/query_range" \
#   --data-urlencode "query=${QUERY}" \
#   --data-urlencode "start=${START_NS}" \
#   --data-urlencode "end=${END_NS}" \
#   --data-urlencode "limit=50" \
#   --data-urlencode "direction=backward" \
# | jq -r '.data.result[].values[] | "\(.[0] | tonumber / 1000000000 | strftime("%Y-%m-%d %H:%M:%S")) | \(.[1])"'
```
