---
metadata:
  kind: incident
  status: final
  source: oncall_case_storage/case-kafka-kraft-livenessprobe-restart-loop.md
  title: "Kafka KRaft Restart Loop: Kubernetes livenessProbe Too Aggressive"
  summary: "Kafka KRaft brokers restarted in rotation with frequent controller role flaps; the root cause was an overly aggressive Kubernetes livenessProbe that killed brokers during startup/jitter; stability was restored by relaxing liveness (prefer startupProbe) while keeping readiness for traffic cutover."
  tags: [kafka, kraft, kubernetes, statefulset, livenessprobe, readinessprobe]
  patterns: [probe-false-positive-restart-loop]
---

# Incident: Kafka KRaft Restart Loop (Kubernetes livenessProbe Too Aggressive)

## 1. Incident Overview
- Date: TBD
- Severity: TBD
- Duration: TBD
- System: Kafka KRaft cluster on Kubernetes (StatefulSet)
- Impact: brokers restarted in rotation; controller role flapped frequently; the cluster could not provide stable service (quantification: TBD)

## 2. System Context
- Architecture (relevant): clients -> Kafka brokers (StatefulSet) -> KRaft quorum (controller election)
- Orchestrator behavior: livenessProbe failures trigger container restarts (can destabilize the quorum)

## 3. Environment
- Platform: Kubernetes
- Kafka mode: KRaft
- Workload type: StatefulSet
- Versions: TBD

## 4. Trigger
- Trigger: restart loop plus controller role flaps (alert name: TBD)

## 5. Impact Analysis
- Blast radius: Kafka cluster-level stability
- User-visible impact: TBD
- Data loss: TBD
- SLO/SLA breach: TBD

## 6. Constraints
- Read-only: describe pods/events/logs
- `#MANUAL`: editing probe config / rolling restart

## 7. Investigation Timeline
- Confirm the restart loop: brokers restart in rotation; controller role changes frequently.
- Check pod events/logs for livenessProbe failures/timeouts.
- Hypothesis: probe sensitivity causes false positives during startup or CPU/IO jitter.

## 8. Root Cause
- Root cause: Kubernetes `livenessProbe` was overly aggressive (`periodSeconds` too short plus `failureThreshold` too low), treating brief jitter as unhealthy; Kubernetes repeatedly restarted brokers, amplifying KRaft controller re-elections into a restart storm.

## 9. Mitigation
- Mitigation: relax livenessProbe sensitivity and roll brokers (`#MANUAL`).
- Example knobs documented in source:
  - increase `failureThreshold`
  - add sufficient `initialDelaySeconds`
  - increase `periodSeconds`
  - keep reasonable `timeoutSeconds`
- Verification:
  - brokers stop restarting
  - controller stops flapping
  - the cluster returns to stable service

## 10. Prevention / Improvement
- Add `startupProbe` for components with long init paths to avoid liveness killing during warmup.
- Keep readiness relatively sensitive for traffic cutover; keep liveness conservative to avoid false kills.
- Alert on controller election frequency and broker restart rate.
- Document probe design rationale and rollback plan.

## 11. Generalizable Lessons
- "Service is restarting" may be orchestrator-driven; before blaming the app, confirm whether probes are causing it.
- For quorum-based stateful systems, forced restarts amplify instability.
- Pattern Card:
  - Pattern name: probe-false-positive-restart-loop
  - When it happens: stateful/quorum services with jittery startups
  - Fast detection signals: pod restarts correlate with probe failures; controller/leader flaps
  - Fast mitigation: relax liveness; add startupProbe
- Common pitfalls: treating liveness as readiness; period too short, threshold too low

## Tags & Patterns
- Tags: kafka, kraft, kubernetes, statefulset, livenessprobe, readinessprobe
- Patterns: probe-false-positive-restart-loop
- First Action: check whether restarts correlate with livenessProbe failures/timeouts

## Evidence Mapping
- Symptom -> "Three brokers restarted periodically" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Symptoms)
- Symptom -> "Controller role flapped frequently" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Symptoms)
- Root cause statement -> "Kafka was not crashing by itself; Kubernetes probes were killing it" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Root Cause)
- Causal chain -> "Kubernetes livenessProbe configuration was overly aggressive" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Root Cause)
- Causal chain -> "periodSeconds too short + failureThreshold too low" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Root Cause)
- Mitigation -> "Edit the Deployment/StatefulSet livenessProbe to allow more recovery time:" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Mitigation)
- Example config -> "failureThreshold: 99" (case-kafka-kraft-livenessprobe-restart-loop.md:Triage - Mitigation)
- Result -> "Brokers became stable and stopped restarting periodically" (case-kafka-kraft-livenessprobe-restart-loop.md:Verify)
