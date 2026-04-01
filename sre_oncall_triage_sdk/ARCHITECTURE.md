# Architecture: SRE Oncall Triage Agent (SDK)

## Design Philosophy

This agent applies SRE reliability principles to LLM-powered automation:

> **An LLM is an unreliable component. The system around it must be reliable.**

The architecture is organized around [GCORF](../sre_oncall_triage_agent/ARCHITECTURE.md) — five dimensions borrowed from production systems design:

| GCORF Dimension | Production System | This Agent |
|-----------------|-------------------|------------|
| **Goal** | SLO: 99.9% availability | Evidence-backed conclusions, conservative language |
| **Controllability** | RBAC + blast radius | Query guard + tier gate + scope declaration |
| **Observability** | Metrics + logs + traces | JSONL execution trace per investigation |
| **Reversibility** | Canary + rollback | Read-only by default, human gate for mutations |
| **Feedback Loop** | Alerting + postmortems | Eval pipeline + case-based learning |

---

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        CLI (cli.py)                          │
│  sre-triage --alert "..." [--llm api|opencode] [--backend http|mcp]  │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│                    Agent Loop (agent.py)                      │
│                                                              │
│  1. Build system prompt (routing table + constraints)        │
│  2. Send alert as user message                               │
│  3. LOOP:                                                    │
│     ┌─────────────────────────────────────────────┐          │
│     │  LLM call → response                        │          │
│     │  if tool_use:                                │          │
│     │    safety_check() → execute_tool() → trace() │          │
│     │    feed result back                          │          │
│     │  if end_turn:                                │          │
│     │    save output + trace → return              │          │
│     └─────────────────────────────────────────────┘          │
│  4. Context budget check → summarize if needed               │
│                                                              │
└────┬──────────┬──────────┬──────────┬────────────────────────┘
     │          │          │          │
┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────┐
│  LLM   │ │ Tools  │ │ Safety │ │ Observability│
│ Client │ │ Layer  │ │ Layer  │ │    Layer     │
└────────┘ └────────┘ └────────┘ └──────────────┘
```

---

## Module Design

### 1. Agent Loop — `agent.py`

The core loop manages the Anthropic Messages API `tool_use` protocol:

```python
while turns < max_turns:
    response = client.messages.create(model, system, messages, tools)

    if response.stop_reason == "end_turn":
        break

    for block in response.content:
        if block.type == "tool_use":
            error = check_safety(block.name, block.input)  # deterministic gate
            if error:
                result = blocked_result(error)
            else:
                result = dispatcher.execute(block.name, block.input)
            tracer.record(block, result)                    # every call traced

    messages.append(assistant_message)
    messages.append(tool_results)

    if context_manager.should_summarize(total_tokens):      # explicit budget
        messages = context_manager.summarize(messages)
```

**Key properties:**
- The loop is backend-agnostic — same code path for Anthropic API and OpenCode
- Every tool call passes through safety checks before execution
- Every tool call is recorded in the trace regardless of success/failure
- Context budget is tracked explicitly, not left to the LLM provider

### 2. LLM Client — Pluggable Backend

```
agent.py
    ↓ client.messages.create()
    ├── Anthropic SDK (default)  ← requires API key
    │     anthropic.Anthropic().messages.create()
    │     Native tool_use protocol
    │
    └── OpenCode Server           ← no API key needed
          POST /session/{id}/message
          Structured JSON output via prompt protocol
```

Both implement the same interface: `client.messages.create(model, system, messages, tools) → Response`.
The agent loop doesn't know which backend is active.

### 3. Tool Layer — `tools/`

```
ToolBackend (Protocol)          ← abstract interface
    │
    ├── HttpVictoriaMetrics     ← default: urllib → /api/v1/query_range
    │     Direct HTTP to VM, Loki, kubectl subprocess
    │     Zero external dependencies (stdlib only)
    │
    └── McpBackend              ← optional: MCP client library
          Delegates to running MCP servers
          Same tool names, different transport
```

**Why both?** The HTTP backend demonstrates understanding of the data source APIs (PromQL, LogQL, kubectl). The MCP adapter demonstrates architectural abstraction. One config switch between them.

**Tool schemas** are defined in Anthropic format (`tools/registry.py`) and passed directly to the Messages API:

| Tool | API | Safety Rules |
|------|-----|-------------|
| `vm_query_range` | VictoriaMetrics `/prometheus/api/v1/query_range` | Label filter required, step >= 30s, window <= 24h |
| `vm_query_instant` | VictoriaMetrics `/prometheus/api/v1/query` | Label filter required |
| `loki_query_range` | Loki `/loki/api/v1/query_range` | Stream selector required, window <= 6h |
| `kubectl_read` | Subprocess (get/describe/logs only) | Tier gate: PROD=read-only, DEV=permissive |
| `lookup_knowledge` | Local file search | None (read-only by nature) |

### 4. Safety Layer — `safety/`

Three deterministic gates, checked before every tool execution:

```
tool_use block
    │
    ├── query_guard.py ──── label filter? step >= 30s? window <= 24h? wildcard check?
    │                        Returns: None (pass) or error string (blocked)
    │
    ├── tier_gate.py ────── cluster alias → tier → policy
    │                        PROD/PCI/MGT/DEMO: block mutations
    │                        PREPROD: block deletes, require --dry-run
    │                        DEV: warn + require INTENT
    │                        UNKNOWN: treat as PROD
    │
    └── scope.py ────────── query references out-of-scope item?
                             Logs expansion, returns warning
```

**Design principle:** Safety is not a prompt. It's a `if error: return blocked_result(error)` in the loop. The LLM cannot bypass it.

The tier gate is a direct Python port of `../sre_oncall_triage_agent/tools/agent_ops/hooks/k8s-gate.sh`:

```python
# Same logic, different runtime
PCI_PATTERN = re.compile(r"^(keastpcia|keastpcib)$")
PROD_PATTERN = re.compile(r"^(kafsouthprod[ab]|kwestprod[ab]|...)$")

def check(command, cluster) -> str | None:
    tier = classify_tier(cluster)
    if tier in ("PROD", "PCI") and MUTATING_PATTERN.search(command):
        return f"BLOCKED: mutating op on {tier} ({cluster})"
    return None  # allowed
```

### 5. Context Management — `context/`

Three-tier strategy to stay within token budgets:

| Tier | Content | When Loaded | Budget |
|------|---------|-------------|--------|
| T1: System Prompt | Routing table + GCORF constraints + query safety | Always | ~3,000 tokens |
| T2: Debug Tree | Matched debug tree + card after routing | After signal extraction | ~2,000-5,000 tokens |
| T3: On-demand | Cases, runbooks, references via `lookup_knowledge` tool | When agent requests | Variable |

**Summarization trigger:** When cumulative input tokens exceed 70% of context window (default 200K), the context manager:
1. Preserves: first message + last 3 turn-pairs
2. Compresses: middle turns into a summary of tool calls + results
3. Tested: 21 messages → 8 messages with no information loss on recent context

### 6. Knowledge Layer — `context/knowledge.py`

Shares the knowledge base with the Claude Code agent (`../sre_oncall_triage_agent/knowledge/`):

```
knowledge/
├── agent-routing-table.md     → loaded into system prompt (T1)
├── debug-trees/ (7 files)     → loaded after routing (T2)
├── cases/ (~34 files)         → searchable via lookup_knowledge tool (T3)
├── runbooks/ (~21 files)      → searchable (T3)
├── cards/ (~15 files)         → searchable (T3)
├── patterns/ (4 files)        → searchable (T3)
└── references/ (32 files)     → searchable (T3)
```

The `KnowledgeLoader` builds an in-memory index from frontmatter metadata (kind, tags, summary) for search. Full file content is loaded only when a match is found.

### 7. Observability — `observability/trace.py`

Every investigation produces a JSONL trace file with three entry types:

```
investigation_start  ──→  turn (per API call)  ──→  tool_call (per tool)  ──→  investigation_end
```

**Tool call entry:**
```json
{
  "type": "tool_call",
  "turn": 2,
  "tool": "vm_query_range",
  "input": {"query": "kube_pod_info{namespace=\"ch\"}", "step": "60s", ...},
  "output_preview": "[[1711900800, 0.342], ...]",
  "success": true,
  "latency_ms": 234.5,
  "safety": {"query_guard": "pass", "scope": "pass", "tier": "PROD/read-ok"},
  "branch": "P95 < 300ms → NON_ACTIONABLE",
  "ts": "2026-03-31T14:23:45+00:00"
}
```

**Investigation summary (end entry):**
```json
{
  "type": "investigation_end",
  "summary": {
    "turns": 3,
    "tool_calls": 2,
    "total_tool_latency_ms": 357.5,
    "total_input_tokens": 12000,
    "total_output_tokens": 750,
    "errors": 0
  }
}
```

This is the agent's equivalent of distributed tracing. Each tool call is a span.

---

## SRE ↔ Agent Mapping

The design is grounded in a structural observation: **SRE and agent engineering are isomorphic problems.** Both build reliable systems from unreliable components. The uncertainty just comes from different sources.

| SRE Concept | Agent Equivalent | Implementation |
|-------------|-----------------|----------------|
| RBAC | Tool-level permissions | `tier_gate.py` — cluster tier → read/write policy |
| Blast radius | Scope declaration | `scope.py` — declared scope vs actual queries |
| Audit log | Execution trace | `trace.py` — JSONL with every tool call |
| Observability | Reasoning trace | Trace captures branch decisions, not just outputs |
| SLI/SLO | Task success rate | Eval pipeline scores routing accuracy, verdict, evidence |
| Error budget | Max turns + safety blocks | Agent stops at `max_turns`, safety blocks count as turns |
| Reconciliation loop | Observe → Plan → Act → Verify | Agent loop: LLM call → tool_use → safety → execute → trace |
| Circuit breaker | Context summarization | Prevents context overflow before it causes degradation |

---

## Data Flow: A Single Investigation

```
1. Alert arrives: "[FIRING] ClickHouse connection refused on port 9000"
   │
2. System prompt loaded (routing table + constraints)
   │
3. LLM Turn 1: Signal extraction + routing
   │  → "Cluster 1: Routing/Ingress. Debug tree: connection-refused-layered"
   │  → tool_call: vm_query_instant({query: 'up{namespace="clickhouse"}'})
   │
4. Safety check: query_guard → PASS (has label filter)
   │
5. Tool execution: HTTP GET to VictoriaMetrics
   │  → Result: [{pod: "clickhouse-0", value: 0}]
   │
6. Trace recorded: tool=vm_query_instant, latency=234ms, safety=pass
   │
7. LLM Turn 2: Interpret result, request next step
   │  → "clickhouse-0 is down. Check endpoints."
   │  → tool_call: kubectl_read({command: "get endpoints -n ch", cluster: "kwestproda"})
   │
8. Safety check: tier_gate → PROD/read-only → PASS (get is read-only)
   │
9. Tool execution: subprocess kubectl
   │  → Result: "clickhouse <none>"
   │
10. LLM Turn 3: Final analysis
    │  → Verdict: NEEDS_ATTENTION
    │  → Evidence chain: [up=0, endpoints=<none>]
    │  → Slack response (hedged language)
    │
11. Output saved: output/sre-triage-2026-03-31_14-04-47.md
12. Trace saved: output/traces/trace-2026-03-31_14-04-47.jsonl
```

---

## What's Not Here (Yet)

| Component | Status | Plan |
|-----------|--------|------|
| Output verifier | Planned | Port `verify.py` from Claude Code agent — 7 schema checks |
| Eval pipeline | Planned | YAML test cases from historical incidents, routing-only + full-loop modes |
| Metrics aggregation | Planned | Token cost, latency percentiles, tool call distribution per investigation |
| MCP adapter | Skeleton | Implement when MCP client library stabilizes |
