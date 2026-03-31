# Signal Extraction

## Purpose

Extract signals from alert text. This is the only authoritative source of facts.

## Principles

- Alert message is the sole truth source
- Extract entities: client names, cluster names, metrics, time ranges
- Do NOT infer or expand scope
- Do NOT assume causality
- Preserve uncertainty

## Process

1. Parse alert text for:
   - Client identifiers
   - Cluster/namespace references
   - Metric names and thresholds
   - Time windows or timestamps
   - Error messages or status codes
   - Resource identifiers (pods, services, nodes)

2. Extract without expansion:
   - Match exact strings only
   - Use case-insensitive matching where appropriate
   - Flag ambiguous matches as uncertain

3. Output structured signals:
   - Extracted entities with confidence levels
   - Ambiguities and unresolved matches
   - Suggested validation steps
