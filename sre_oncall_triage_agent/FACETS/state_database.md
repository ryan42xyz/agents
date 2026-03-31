# State Database

## Purpose

Inspect database and state storage health.

## Scope

- Database cluster health
- Backlog and queue depths
- Connection pool metrics
- Transaction rates and latencies

## Inspection Checklist

1. YugabyteDB dashboard
   - Cluster health and replication
   - Node-level metrics
   - Database connection status

2. State storage metrics
   - Backlog sizes and trends
   - Queue processing rates
   - State transition latencies

3. Database performance
   - Query latencies
   - Connection pool utilization
   - Transaction throughput

## Principles

- Database issues can cascade to application layer
- Check backlog as early indicator
- Consider replication lag if multi-region
- Do NOT assume database is root cause without evidence
