---
metadata:
  kind: runbook
  status: draft
  summary: "Card: First hour of a Yugabyte incident - stabilization actions (traffic/MM), restart priority order, and key verification points."
  tags: ["card", "yugabyte", "incident", "recovery", "mirrormaker", "oncall"]
  first_action: "Reduce blast radius first (shift traffic + stop MirrorMaker) (#MANUAL)"
---

# Card: Yugabyte Incident - First Hour

## TL;DR (Do This First)
1. Reduce blast radius: shift traffic / stop MirrorMaker (`#MANUAL`)
2. Verify the cluster is reachable, and identify what is overloaded
3. Only then consider restarts/rollouts (`#MANUAL`)

## Why Ordering Matters
- Scaling upstream when the DB has no headroom will amplify the failure.
- Stopping MM/shifting traffic can immediately reduce write pressure.

## Further Reading (Deep Doc)
- Full runbook: [runbook-yugabyte-incident-recovery-steps.md](./runbook-yugabyte-incident-recovery-steps.md)
