# Logs Evidence

## Purpose

Gather log evidence to support or refute hypotheses from other facets.

## Principles

- Logs provide evidence, not causality
- Use logs to validate signals from other facets
- Do NOT search logs blindly without hypothesis
- Preserve context and timestamps

## Inspection Checklist

1. Central logging dashboard
   - Search by extracted entities (client, cluster, pod)
   - Filter by time window around alert
   - Look for error patterns or anomalies

2. Structured log queries
   - Error logs matching alert context
   - Warning patterns preceding alert
   - Correlation with metrics from other facets

3. Log aggregation and patterns
   - Frequency of errors over time
   - Unique error signatures
   - Correlation with resource or traffic changes

## Process

1. Use signals from signal_extraction facet
2. Formulate hypothesis from other facets
3. Search logs to validate or refute
4. Document evidence without drawing conclusions
