# SRE Oncall Triage Agent — SDK Implementation

Standalone SRE oncall triage agent built on the Anthropic Messages API. Takes a production alert as input, autonomously investigates using metrics/logs/kubectl, and produces an evidence-backed investigation report.

This is a from-scratch reimplementation of an existing [Claude Code skill-based agent](../sre_oncall_triage_agent/) at the SDK level — managing the tool_use loop, context window, safety gates, and execution tracing in application code instead of relying on an agent framework.

## Why This Exists

Most agent projects demonstrate prompt engineering. This one demonstrates **agent systems engineering**: the same reliability principles (blast radius, audit trails, SLI/SLO) that keep production systems running, applied to an LLM-powered investigation pipeline.

The architecture treats the LLM as an unreliable component inside a reliable system — exactly how SRE treats any service dependency.

## Quick Start

```bash
# Install
cd agents/sre_triage_sdk
python3 -m venv .venv && .venv/bin/pip install -e .

# Configure
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

# Dry run (no API call)
ANTHROPIC_API_KEY=sk-test .venv/bin/sre-triage --dry-run \
  --alert "[FIRING] ClickHouse connection refused on port 9000, cluster: aws-uswest2-prod-a"

# Run investigation
.venv/bin/sre-triage --alert "[FIRING] ClickHouse connection refused on port 9000"

# Run tests (no API key needed)
.venv/bin/python tests/test_integration.py
.venv/bin/python tests/test_agent_loop.py
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

```
Alert text
  → Agent Loop (agent.py)
      → LLM call (Anthropic API or OpenCode)
      → stop_reason == tool_use?
          → Safety check (query_guard + tier_gate + scope)
          → Execute tool (HTTP backend or MCP)
          → Record trace (JSONL)
          → Feed result back → next LLM call
      → stop_reason == end_turn?
          → Save output + trace
          → Return investigation report
```

### Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| LLM interface | Anthropic Messages API (`tool_use` protocol) | Native structured tool calls, no prompt-based JSON parsing |
| Tool layer | Direct HTTP to VM/Loki + `ToolBackend` Protocol | Shows understanding of data source APIs, not just MCP abstraction |
| Safety | Code-level query guard + tier gate | Deterministic enforcement — not prompt-based guardrails |
| Observability | JSONL execution traces | Every tool call recorded with input/output/latency/safety checks |
| Context mgmt | 3-tier strategy with explicit token budgets | System prompt (always) → debug tree (on routing) → knowledge (on demand) |

## Project Structure

```
src/sre_triage/
├── agent.py                  # Core agent loop (Messages API + tool_use)
├── cli.py                    # CLI entry point
├── config.py                 # Environment-based configuration
│
├── context/
│   ├── knowledge.py          # Knowledge base loader (routing table, debug trees, search)
│   └── manager.py            # Context window budget + summarization
│
├── tools/
│   ├── base.py               # ToolBackend Protocol (the abstraction boundary)
│   ├── registry.py           # Tool schema definitions + dispatch
│   ├── http/
│   │   └── victoriametrics.py  # Direct HTTP backend (urllib, zero deps)
│   └── mcp/
│       └── adapter.py        # MCP client adapter (optional)
│
├── safety/
│   ├── query_guard.py        # PromQL/LogQL validation (label filters, step, window)
│   ├── tier_gate.py          # Cluster tier enforcement (PROD→read-only, DEV→permissive)
│   ├── scope.py              # Investigation scope tracking
│   └── human_gate.py         # Interactive confirmation for mutations
│
├── observability/
│   └── trace.py              # JSONL execution trace with per-tool-call metrics
│
├── llm/
│   └── claude_code.py        # OpenCode server backend (alternative to API)
│
├── output/                   # Report renderer + verifier (planned)
└── eval/                     # Evaluation pipeline (planned)
```

## What's Implemented

| Module | Status | Lines | Tested |
|--------|--------|-------|--------|
| Agent loop (`agent.py`) | Complete | 346 | Mock 3-turn test |
| Tool schemas + dispatch | Complete | 213 | Integration test |
| HTTP backend (VM/Loki/kubectl) | Complete | 143 | — |
| Query guard | Complete | 107 | 6 safety rules |
| Tier gate | Complete | 110 | All 6 tiers |
| Knowledge loader | Complete | 128 | Real data test |
| Context manager | Complete | 73 | Summarization test |
| Execution tracer | Complete | 160 | JSONL output test |
| CLI | Complete | 145 | Dry-run test |
| MCP adapter | Skeleton | 47 | — |
| Output verifier | Planned | — | — |
| Eval pipeline | Planned | — | — |

## Tests

```bash
# Integration tests — validates safety, knowledge, tracing, tool dispatch
.venv/bin/python tests/test_integration.py
# 8 tests, all pass

# Agent loop test — full 3-turn investigation with mocked API
.venv/bin/python tests/test_agent_loop.py
# Validates: tool_use cycle, trace generation, output file creation
```

## Safety Model

Three layers, all enforced in application code:

**Layer 1: Query Guard** — Every PromQL/LogQL query validated before execution:
- Label filter required (no unscoped queries)
- Step >= 30s, window <= 24h (VM) / 6h (Loki)
- No wildcard regex on high-cardinality labels

**Layer 2: Tier Gate** — Cluster alias → environment tier → access policy:
- PROD/PCI/MGT: read-only, all mutations blocked
- PREPROD: read + dry-run, deletes blocked
- DEV: permissive with INTENT required
- Unknown: treated as PROD (conservative default)

**Layer 3: Scope Tracking** — Validates tool calls against declared investigation scope.

## Trace Format

Every investigation produces a JSONL trace file:

```jsonl
{"type":"investigation_start","investigation_id":"2026-03-31_14-04-47","ts":"..."}
{"type":"turn","turn":1,"role":"assistant","tokens_in":3000,"tokens_out":150,"ts":"..."}
{"type":"tool_call","turn":1,"tool":"vm_query_range","input":{...},"output_preview":"...","latency_ms":234.5,"safety":{"query_guard":"pass","tier":"PROD/read-ok"},"ts":"..."}
{"type":"investigation_end","summary":{"turns":3,"tool_calls":2,"total_input_tokens":12000},"ts":"..."}
```

## Relationship to Claude Code Agent

| Dimension | Claude Code Skill | This Project (SDK) |
|-----------|------------------|-------------------|
| Runtime | Claude Code session | Standalone Python process |
| Tool access | MCP servers | Direct HTTP + MCP adapter |
| Safety | Shell hooks (k8s-gate.sh) | Python code (query_guard.py, tier_gate.py) |
| Context mgmt | Claude Code auto-manages | Explicit 3-tier strategy with token budgets |
| Observability | Hook-based JSONL | Code-level JSONL trace |
| Evaluation | None | YAML test cases + scorer (planned) |
| Knowledge base | Shared | Shared (same `../sre_oncall_triage_agent/knowledge/`) |

Both coexist. Claude Code version for daily oncall (convenient). SDK version for portfolio + evaluation experiments.

## Dependencies

```
anthropic>=0.40.0    # LLM client
click>=8.0           # CLI
pyyaml>=6.0          # Config/eval
```

All tool implementations use `urllib.request` (stdlib). Zero external dependencies for data source access.
