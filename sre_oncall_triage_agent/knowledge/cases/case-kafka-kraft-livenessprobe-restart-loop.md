---
metadata:
  kind: case
  status: final
  summary: "Root cause of periodic restarts for Kafka KRaft brokers: an overly aggressive Kubernetes livenessProbe causes false kills and frequent controller re-elections; mitigate by loosening probe thresholds and/or adding a startupProbe to stop the restart storm and restore stability."
  tags: ["kafka", "kraft", "k8s", "livenessprobe"]
  first_action: "Start from events: correlate restarts with livenessProbe failures"
---

# Kafka KRaft Periodic Restart Loop (livenessProbe False Kills)

## TL;DR (Do This First)
1. Confirm the restart pattern: brokers restart in rotation + controller role flaps frequently
2. Check whether restarts line up with `Liveness probe failed` in pod events
3. Stop the bleeding by reducing liveness sensitivity (`#MANUAL`), then observe stability

## Safety Boundaries
- Read-only: describe pods/events/logs
- `#MANUAL`: change probe config / roll brokers

## Triage
- Confirm the trigger: `kubectl describe pod <broker>` shows `Liveness probe failed` around each restart.
- Before blaming probes, rule out obvious self-crash signals (OOMKilled, fatal JVM exits, etc.).
- KRaft signature: after false kills, you see repeated controller elections / frequent controller role switches.

Representative checks:

```bash
kubectl get pods -l app=kafka -o wide
kubectl describe pod kafka-0
kubectl logs kafka-0 | grep -i controller
```

Mitigation (`#MANUAL`): for quorum-based stateful systems, make liveness more conservative.

```yaml
livenessProbe:
  failureThreshold: 99
  initialDelaySeconds: 50
  periodSeconds: 50
  timeoutSeconds: 5
```

Note: `readinessProbe` can be more sensitive to shed traffic; the restart storm is caused by liveness false kills.

## Verification
- Observe for >= 30-60 minutes after the change.
- `RESTARTS` stops increasing; controller role is stable; client errors/timeouts return to baseline.
- Kafka pods stop producing new `Liveness probe failed` events.

## Closeout
- Close when all are true: no restart-loop recurrence for >= 60 minutes, controller stable, alerts cleared, and probe change recorded (what/why/how rolled out).
- References:
  - [Kubernetes Liveness and Readiness Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
  - [Kafka KRaft Controller](https://kafka.apache.org/documentation/#kraft)

## One-line Essence
An overly aggressive Kubernetes livenessProbe can falsely kill Kafka KRaft brokers, triggering controller flaps and a restart storm; for stateful systems, keep liveness more conservative.
