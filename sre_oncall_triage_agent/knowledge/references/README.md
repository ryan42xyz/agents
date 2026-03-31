# References (not tracked in git)

This directory contains internal operational reference material:

- Internal API endpoints and Grafana dashboard URLs
- Customer/client name mappings
- Cluster-specific configurations and links
- Monitoring tool endpoints and credentials

These files are **gitignored** because they contain company-specific information. They are used locally by the agent for link generation and operational lookups.

## Expected files

| File pattern | Purpose |
|---|---|
| `reference-clients.md` | Client name → label mapping |
| `reference-clusters.md` | Cluster aliases and environment tiers |
| `reference-link-templates.md` | Grafana / VMUI / alert deep-link templates |
| `reference-grafana-dashboards.md` | Dashboard parameter templates |
| `reference-kubernetes.md` | kubectl command templates |
| `reference-defaults.md` | Default parameter values |
| `reference-*.md` | Other operational references |

## Setup

Copy the reference files from your internal knowledge base, or create them following the frontmatter schema in `../CLAUDE.md`.
