---
metadata:
  kind: pattern
  status: draft
  summary: "Production-grade root cause analysis for ClickHouse CPU spikes: starting from MergeTree merge and mutation mechanics, separate symptoms from root causes, provide signals/metrics/steps, and summarize mitigations via throttling, tuning, and write-governance to reduce merge pressure."
  tags: ["clickhouse", "cpu", "merge", "mutation", "performance"]
  first_action: "Confirm CPU is from MergeMutate (merge pressure), not queries"
---

# ClickHouse CPU Saturation: Root Cause Analysis and Fixes

Your reasoning chain is **correct overall and already close to a production-grade root cause**.
I will tighten it from a system perspective so you can tell what is a "root cause" vs what is just a "symptom".

I will not repeat what you already said; I will only give the **core decision model**.

---

## TODO - ClickHouse issue

1. **Memory too high**
   - Crashing
     - Slow down merge / mutation
     - Memory limit too high, bigger than requests limit
2. **CPU too high**
    - Too many tenants -> remove useless clients (@qa team)

---

## 1. Start with symptoms (not the cause)

From `top`:

```
MiB Mem : 31386.8 total,   722.9 free,  16768.6 used,  13895.3 buff/cache
MiB Swap:     0.0 total,     0.0 free,      0.0 used.  14147.7 avail Mem

  PID USER      PR  NI    VIRT    RES    SHR S  %CPU %MEM     TIME+ COMMAND
  662 clickho+  20   0  262.8g   7.3g 125696 R  60.9 23.8 144:12.64 MergeMutate
  666 clickho+  20   0  262.8g   7.3g 125696 R  56.5 23.8 139:40.00 MergeMutate
  669 clickho+  20   0  262.8g   7.3g 125696 R  56.5 23.8 150:57.30 MergeMutate
  673 clickho+  20   0  262.8g   7.3g 125696 R  56.5 23.8 142:01.21 MergeMutate
  663 clickho+  20   0  262.8g   7.3g 125696 R  52.2 23.8 143:45.77 MergeMutate
   91 clickho+  20   0  262.8g   7.3g 125696 S   8.7 23.8  44:43.80 TraceCollector
  6778 root      20   0   11376   4480   2944 R   8.7  0.0   0:00.04 top
  705 clickho+   20   0  262.8g   7.3g 125696 S   4.3 23.8   1:20.50 Common
    1 clickho+   20   0  262.8g   7.3g 125696 S   0.0 23.8   0:00.61 clickhouse-serv
```

This shows:

- CPU is almost entirely consumed by **merge background threads**
- It is not query CPU
- It is not user traffic
- It is internal storage engine compaction

This conclusion is **certain**.

---

## 2. First principles of ClickHouse CPU saturation

ClickHouse CPU is not equal to queries.
ClickHouse CPU = **merge**.

### What merge is

MergeTree design:

```
Many small parts written
↓
Background continuously merges into larger parts
↓
Otherwise queries get slower and slower
```

So:

> More writes -> more parts -> more merges -> higher CPU

This is a hard rule.

---

## 3. Your direct-cause hypothesis is mostly correct

You wrote:

> Writes are too heavy -> snapshot -> restore -> unmerged part backlog -> sustained merge -> high CPU

Yes: **the logic is correct**.

### Primary cause (direct cause, on-site conclusion)

- **Resource limits are too small**: the system cannot keep up and hits a bottleneck
- **Direct description of ClickHouse high CPU**:
  ClickHouse CPU is full, probably because the amount of writing is too large when doing EBS snapshot, which triggers a large number of background merge. Even after preprod recovers the data, the part that has not been merged before will continue to merge, so the CPU will still be very high.

**Verification: check currently running merges**

```sql
SELECT
    database,
    `table`,
    num_parts,
    result_part_name,
    elapsed,
    progress,
    is_mutation,
    (total_size_bytes_compressed / 1024) / 1024 AS size_mb
FROM system.merges
```

Example result:

| _database | _table          | _num_parts | _result_part_name                     | _elapsed     | _progress | _is_mutation | _size_mb  |
|-----------|-----------------|------------|----------------------------------------|--------------|----------|--------------|-----------|
| onefinance | detection_store | 8          | 202602_1646768_1647103_4               | 51.6         | 0.38     | 0            | 1531.58   |
| onefinance | event_result    | 100        | 202602_34504809_34504908_2             | 7.76         | 0        | 0            | 49.59     |
| onefinance | event_result    | 99         | 202602_34504709_34504807_2             | 7.76         | 0        | 0            | 44.47     |
| onefinance | event_result    | 100        | 202602_34504911_34505010_2             | 6.70         | 0        | 0            | 45.19     |
| nymbus    | event_result    | 34         | 202602_2610005_2610038_2               | 3.00         | 0        | 0            | 25.76     |
| evoluve   | event_result    | 6          | 202602_3223995_3224009_3               | 2.37         | 1        | 0            | 4.53      |
| onefinance | event_result    | 12         | 202602_34505011_34505022_2             | 0.40         | 0        | 0            | 4.06      |

But here is a production-grade key point to add:

### High CPU after snapshot restore is not abnormal

It is because:

```
Restore data = restore many unmerged small parts
↓
ClickHouse considers the system "unorganized"
↓
Starts aggressive background merges
↓
CPU stays at 100%
```

This is not a bug; it is by design.

ClickHouse will:

> It would rather burn CPU
> than leave parts unorganized

Because otherwise queries can become unbearably slow.

---

## 4. The real first-principles root cause (one step missing)

You are currently saying:

> Small resources cause merge to not keep up

That statement is **only half true**.

The real root cause should be framed like this:

### Root cause is not "CPU is small"

### Root cause is: merge debt

---

### Merge debt model (core)

As long as:

```
Write-driven part creation rate > merge consumption rate
```

the system enters:

> merge debt accumulation mode

Then:

```
Even if writes stop
CPU stays at 100%
Until the merge debt is paid
```

That is your current state.

---

## 5. Your system.parts output is already strong evidence

Look at this:

```
trace_log_2   873GB   102 parts
processors_profile_log 268GB
query_log 56GB
```

These are not business tables. They are:

> ClickHouse internal profiling logs

And:

> huge + many parts

This suggests:

```
Profiling log write volume is huge
↓
Creates a massive number of small parts
↓
merge backlog
↓
CPU stays saturated long-term
```

This is the real secondary cause. Snapshot is only a trigger. The long-term CPU killer is:

> internal log tables exploding in size

### Secondary cause (indirect cause)

Symptom: **profiling and trace tables are too large**.

**How to check: exec into the pod and inspect table parts and sizes**

```bash
# k get pod -n preprod | grep chi
chi-dv-datavisor-0-0-0    2/2  Running  1 (27h ago)  27h

kubectl exec -it -n prod chi-dv-datavisor-0-0-0 -- bash
clickhouse-client
```

```sql
SELECT
    `table`,
    sum(rows) AS rows,
    ((sum(bytes_on_disk) / 1024) / 1024) / 1024 AS gb,
    count() AS parts
FROM system.parts
WHERE active = 1
GROUP BY `table`
ORDER BY gb DESC
LIMIT 10
```

Example result:

| table                      | rows        | gb     | parts |
|----------------------------|-------------|--------|-------|
| trace_log_2                | 47704222724 | 873.01 | 102   |
| detection_store            | 128233912   | 340.49 | 104   |
| processors_profile_log_0   | 10637842734 | 268.61 | 92    |
| event_result               | 118270653   | 73.14  | 505   |
| query_log_3                | 31503155    | 56.76  | 83    |
| alert_events               | 19037806    | 50.36  | 212   |
| trace_log_0                | 2276675424  | 42.61  | 17    |
| metric_log_3               | 56532206    | 20.78  | 87    |
| trace_log                  | 434720144   | 11.38  | 23    |
| asynchronous_metric_log_2  | 11568507638 | 8.56   | 81    |

---

## 6. The complete reasoning chain (most correct version)

### Layer 1 (symptoms)

```
CPU 100%
MergeMutate threads saturated
```

### Layer 2 (direct cause)

```
Many background merges running
```

### Layer 3 (system cause)

```
Huge merge backlog (merge debt)
```

### Layer 4 (triggers)

Two sources:

#### A. Snapshot restore

```
Restore many small parts
→ merge backlog
```

#### B. Profiling logs exploding (more long-term)

```
trace_log / query_log / profile_log
Write volume is huge
-> small parts explode
-> sustained merge pressure
```

---

## 7. Your proposed direction is right, but incomplete

You said:

> Reduce merge threads

This is:

> mitigation to reduce CPU
> not a cure

Because:

```
merge thread ↓
merge throughput ↓
merge debt lasts longer
```

This only turns 100% CPU into 50%, but lasts longer.

### What was tried on-site

The attempt to reduce CPU usage was essentially **reducing merge threads** by changing ClickHouse configuration.

> We've tried this manually in useat preprod, where we can make the merge thread smaller.

---

## 8. Production-grade solutions (by priority)

### Priority 1 (must do)

#### Limit internal profiling logs

These tables:

```
trace_log
query_log
processors_profile_log
metric_log
```

They are **for debugging**, not business.

**Method 1: reduce logging**

```
log_queries = 0
log_query_threads = 0
log_processors_profiles = 0
log_profile_events = 0
```

Or reduce flush frequency.

**Method 2: TTL auto cleanup**

Add to these tables:

```
TTL event_time + INTERVAL 3 DAY DELETE
```

Otherwise:

> merges will never finish

---

### Priority 2

#### Limit merge concurrency (short-term stop the bleeding)

You can tune:

```
background_pool_size
background_merges_mutations_concurrency_ratio
max_bytes_to_merge_at_max_space_in_pool
```

This is:

> throttle merges -> reduce CPU

---

### Priority 3 (long-term)

#### Control part count

Core idea:

> reduce small part creation

Methods:

```
Increase insert batch size
Reduce frequent small writes
Disable unnecessary logs
```

---

## 9. Final assessment

You asked:

> Is this reasoning chain correct?

### Yes, ~80% correct

But it is missing one key sentence:

> It is not that resources are too small
> it is that merge debt is too large

Small resources only mean:

> you cannot pay down the debt quickly

The real problem is:

> merge debt created by writes + logs is too large

---

## 10. One-sentence rule (production-grade)

In the future, whenever you see:

```
clickhouse CPU 100%
top = MergeMutate
```

Do not overthink it:

> it is merge debt
> not queries
> not just "resources"
> it is a part backlog

Then immediately check:

```
system.parts
system.merges
system.part_log
```

You can solve 90% of cases quickly.

---

## Appendix: ClickHouse config reference

```xml
<background_pool_size>4</background_pool_size>

<merge_tree>
  <max_suspicious_broken_parts_bytes>3298534883328</max_suspicious_broken_parts_bytes>
  <number_of_free_entries_in_pool_to_lower_max_size_of_merge>3</number_of_free_entries_in_pool_to_lower_max_size_of_merge>
  <number_of_free_entries_in_pool_to_execute_mutation>2</number_of_free_entries_in_pool_to_execute_mutation>
  <number_of_free_entries_in_pool_to_execute_optimize_entire_partition>2</number_of_free_entries_in_pool_to_execute_optimize_entire_partition>
  <min_bytes_for_wide_part>10737418240</min_bytes_for_wide_part>
  <allow_remote_fs_zero_copy_replication>false</allow_remote_fs_zero_copy_replication>
</merge_tree>
```
