---
metadata:
  kind: pattern
  status: final
  summary: "General root-cause model and debug flow for intermittent Ingress 429: explains the mismatch between short rate-limit windows (1s/5s) and 1m averaged metrics, how to verify window and burst settings, align short-window QPS with 429 spikes, and validate causality between config and traffic shape."
  tags: ["ingress", "rate-limit", "429", "traffic"]
  first_action: "Align short window QPS (1s/5s) with 429 spikes"
---

> The only case family
> 
> 
> Everything you listed: 429, burst, window mismatch, partial cases
> 
> all reduce to this.
> 

---

## Trigger signals (any)

- Client intermittent failures
- Ingress shows intermittent 429
- 1m QPS / SLA looks normal

---

## Core call (first principles)

> Rate limiting works on a "time window", not on SLA or 1m averages
> 

When:

- global rate limit uses a **1s/5s window**
- real traffic is **bursty**
- but what you observe is **1m average QPS**

-> **429 can be a "config is correct but the mental model is wrong" symptom**

---

## Debug flow (the only correct path)

### Step 1: Confirm Ingress rate limit configuration

```bash
kubectl get ingress -A -o yaml | grep -E"global-rate-limit"

```

Focus on:

- rate limit window (1s/5s/1m)
- burst / limit parameters

---

### Step 2: Align short-window metrics

- Pull **1s/5s QPS**
- Align **429 spike timestamps**

Decide:

- whether burst is strongly correlated with 429

---

### Step 3: Log validation (optional, but helpful)

- ingress / Loki logs
- Look for rate-limit markers / reject logs

---

## Verify

- 429 spikes align with 1s/5s window QPS spikes
- window/burst in config matches expected traffic (or the mismatch is escalated/recorded)

---

## Decision (condensed)

- **Default**: `monitor`
- **Escalate** only when:
    - client failures persist, and
    - 429 is strongly correlated with short-window bursts, and
    - current window/burst config does not match expected traffic

> You only have 1 historical escalate case here, which is healthy
> 

---

## Allowed action boundaries

- Do not blindly increase limits
- Do not look only at 1m QPS
- Make the short-window behavior explicit
- Use evidence to decide escalation

---

## Exit Criteria

- 429 is explainable by short-window bursts
- no sustained SLA regression
- blast radius does not expand

-> Close / keep monitoring

---

## Consolidation of historical sub-cases

| Historical label | Actual bucket |
| --- | --- |
| bursty traffic window mismatch | Ingress 429 short-window spikes |
| 1s window burst throttle | Ingress 429 short-window spikes |
| 429 window mismatch | Ingress 429 short-window spikes |
| partial / missing case.json | Ingress 429 short-window spikes (insufficient evidence) |

---
