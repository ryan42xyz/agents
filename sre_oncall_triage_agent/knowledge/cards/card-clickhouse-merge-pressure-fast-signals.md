---
metadata:
  kind: pattern
  status: draft
  summary: "Card: ClickHouse merge pressure fast signals (MergeMutate CPU, parts explosion, system.merges) and first-line safe mitigations."
  tags: ["card", "clickhouse", "cpu", "merge", "parts", "performance", "oncall"]
  first_action: "First confirm CPU is from MergeMutate/merge pressure, not queries"
---

# Card: ClickHouse Merge Pressure - Fast Signals

## TL;DR (Do This First)
1. Confirm CPU is mostly consumed by merge/mutation threads (not queries)
2. Look for insert delay/backpressure signals (parts explosion)
3. Decide: reduce write pressure vs increase merge capacity (`#MANUAL` depends on the environment)

## Key Signals
- Host `top`: `MergeMutate` high CPU
- Logs: `Delaying inserting block ... because there are ... parts`
- `system.merges` shows long-running merges and many parts

## Minimal SQL
```sql
SELECT * FROM system.merges LIMIT 10;
```

## Practical Notes
- Kafka lag may be a symptom of downstream ClickHouse write backpressure.
- Do not treat random restarts as the first action; capture evidence first, then pick a lever.

## Further Reading (Deep Doc)
- Full RCA pattern: [pattern-clickhouse-merge-cpu-root-cause.md](./pattern-clickhouse-merge-cpu-root-cause.md)
