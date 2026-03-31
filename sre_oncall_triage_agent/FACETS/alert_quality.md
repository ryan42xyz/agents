# Alert Quality

## Purpose

Validate whether the alert itself is reliable before diving into system inspection.

## Principles

- Alerts can be false positives
- Alerts can be flapping or transient
- Alert rules may be misconfigured
- Always validate alert before deep inspection

## Inspection Checklist

1. VMAlert rule validation
   - Check if rule is still active
   - Verify rule configuration
   - Check rule evaluation frequency

2. Alert firing validation
   - Check if alert is currently firing
   - Verify alert is not flapping
   - Check if alert is transient (already resolved)

3. Alert context validation
   - Verify alert time window is correct
   - Check if alert conditions are still met
   - Validate alert matches current system state

4. Historical context
   - Check alert history for same rule
   - Identify patterns in alert firing
   - Check if alert correlates with known maintenance windows

## Process

1. Always start by validating alert quality
2. If alert is invalid/flapping, flag before proceeding
3. If alert is valid, proceed to other facets
4. Document alert validation results in checklist
