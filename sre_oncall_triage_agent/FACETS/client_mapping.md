# Client Mapping

## Purpose

Use client list as reference for name matching and validation only.

## Principles

- Client list is NOT authoritative
- Used only for validation, not scope expansion
- Never assume a client is affected unless explicitly mentioned in alert
- Preserve exact client names from alert text

## Process

1. Match client names from alert text against reference list
2. Validate spelling and variations
3. Do NOT:
   - Expand to related clients
   - Infer client scope
   - Suggest additional clients to check
4. Suggest inspection paths if client name is ambiguous

## Output

- Matched client names (with confidence)
- Ambiguous matches requiring human validation
- Suggestions for where to inspect client-specific metrics
