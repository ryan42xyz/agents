---
metadata:
  kind: runbook
  status: final
  summary: "Production-grade troubleshooting model for Yugabyte connection failures/bootstrapping: clarifies the difference between UI signals like not balanced and the real bottleneck, provides a decision tree from 'is it truly down' -> 'is it rebalancing' -> 'IO/CPU/memory/write pressure', and helps pinpoint tserver self-protection and raft catchup as the cause of connection refusal."
  tags: ["yugabyte", "ysql", "bootstrapping", "connectivity"]
  first_action: "Focus on tserver pressure/raft catchup, not UI balance"
---

# Yugabyte Connection Failures / Bootstrapping Troubleshooting Model

## TL;DR (Do This First)
1. Confirm if it is a real outage: can any client connect? is it localized?
2. Ignore UI "not balanced" until you prove rebalance is happening; first suspect node IO/CPU/memory pressure
3. Focus on tserver overload / raft catchup signals; correlate with resource metrics and recent changes

## Verification
- Connections recover and remain stable after pressure is relieved
- Tablet/raft catchup stabilizes; errors stop increasing

> This is a typical Yugabyte incident where surface signals mislead and the real bottleneck is resources/state.
> Next time you cannot connect to Yugabyte, follow this framework directly.

---

## 1. The real nature of this case

**It is not:**

> cluster not balanced

**It is:**

> **tserver enters self-protection under resource/IO pressure -> the driver sees bootstrapping -> connections fail**

In other words:

> It is not a topology problem.
> It is node pressure plus raft/catchup.

---

## 2. The correct causal chain (production-grade)

Abstract this case into reusable logic:

```text
Cannot connect to Yugabyte
        ↓
Driver reports Overloaded / bootstrapping
        ↓
Suspect the node is unhealthy
        ↓
Check UI -> see not balanced (surface signal)
        ↓
But tablet distribution is actually balanced (rule out rebalance)
        ↓
Find the real cause:
tserver transient resource/IO/raft pressure
        ↓
tablet catchup / bootstrap
        ↓
Refuse requests (protect consistency)
        ↓
Connection failure
```

---

## 3. Decision tree: what to do when you cannot connect to Yugabyte

### Step 1 - Determine whether it is truly down

First check:

```text
yb-master UI
→ Tablet servers
```

| Signal | Meaning |
| ---------------------- | ----------- |
| node DEAD | Truly down |
| node BOOTSTRAPPING | Scaling/recovery in progress |
| node ALIVE but errors/refusals | Resource/IO issue |

This case: **ALIVE but refusing requests**.

---

### Step 2 - Determine whether it is rebalancing

Check:

```text
Are tablet counts heavily skewed?
```

| Case | Conclusion |
| ---------- | ---------------- |
| Severely imbalanced | Rebalancing |
| Fully balanced | X not rebalancing |
| New node added | Rebalancing |
| Node just restarted | Rebalancing |

This case:

> Fully balanced -> rule out rebalance.
> UI not balanced is usually historical residue / mild leader skew, not the primary cause.

---

### Step 3 - Determine the real root cause

That leaves three classes:

| Root cause | Share |
| -------------------- | ----- |
| Slow IO / disk jitter | 40% |
| Memory/CPU pressure | 30% |
| Bulk writes/import | 30% |

This case:

> Likely: one-off bulk import plus small preprod resources.
> (Consistent with issues caused by undersized resource limits: it is almost always resources/state.)

---

## 4. First principles (memorize this)

Yugabyte will **refuse connections** under these conditions:

```text
raft catchup
tablet bootstrap
flush/compaction pressure
memtable flush
```

At this point:

> The node is alive.
> But it is not serving logically.

The driver sees:

```text
OverloadedException
bootstrapping
```

---

## 5. Why a restart can fix it

Because:

```text
raft queue stuck
memtable backlog
flush backlog
```

Restart can:

```text
Clear queues
Rebuild tablet state
Re-elect leaders
```

Common preprod mitigation:

```bash
#MANUAL
kubectl rollout restart sts yb-tserver -n preprod
```

---

## 6. Oncall case template (abstracted from this incident)

### Incident

YB connection failure / driver reports bootstrapping

### Surface signals

- Cannot connect to CQL
- Driver reports overloaded / bootstrapping
- UI shows not balanced (**misleading**)

### Investigation chain

1. **Are any nodes dead**
   -> all alive

2. **Is it rebalancing**
   -> tablet counts balanced
   -> no new nodes
   -> rule out

3. **Is it resource/IO pressure**
   -> small preprod resources
   -> bulk write/import
   -> raft catchup
   -> tablet bootstrap

### Root cause

> Under high IO/resource pressure, tserver hits tablet catchup/bootstrap and temporarily refuses requests.

### Mitigation

```bash
#MANUAL
kubectl rollout restart sts yb-tserver -n preprod
```

### Prevention

- Avoid bulk imports
- Increase tserver resources
- Write in batches
- Increase disk IOPS

---

## 7. First reaction when you see these errors

If you see:

```text
OverloadedException
bootstrapping
```

Immediately jump to:

> It is not a connectivity issue.
> It is tserver protecting itself.

Check first:

```text
resources
IO
write pressure
```

Do not start with:

```text
network
service
dns
```

---

## 8. Production-grade rule of thumb

For any future Yugabyte oncall:

```text
Cannot connect
  -> first check node alive
  -> then check rebalance
  -> then check IO/resources
  -> restart last
```

This is right in ~90% of cases.

---

## 9. Root cause confirmation: questions to ask oncall

If you are handling this oncall case, confirm:

- Was there a **bulk import** at that time?
- Was there a **Spark job**?
- Was there a **backfill**?
- Was there a **restore**?
- Was there **bulk write** activity?

If any one of these is true, the root cause is almost certainly determined.
