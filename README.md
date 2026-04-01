# SRE Oncall Triage Agent — Two Implementations

Two implementations of the same SRE oncall triage agent, at different abstraction layers. Same domain, same knowledge base, different engineering surface.

## The Two Agents

```
agents/
├── sre_oncall_triage_agent/   # Claude Code skill (product layer)
└── sre_oncall_triage_sdk/     # Standalone Python agent (SDK layer)
```

### `sre_oncall_triage_agent/` — Claude Code Skill

The production version. Runs inside a Claude Code session as a skill + hook chain.

- **130+ knowledge files**: routing table, 7 debug trees, ~34 case studies, ~21 runbooks
- **6 triage clusters**: Routing/Ingress, Scheduling/Node, Stateful Write, False Signals, Identity, Change Management
- **3 safety layers**: Claude Code permissions → shell hook chain (k8s-gate.sh) → agent spec constraints
- **MCP tool integration**: VictoriaMetrics, Grafana Loki, kubectl (via MCP servers)
- **Output verification**: `verify.py` with 7 structural checks (PASS/WARN/FAIL)

The Claude Code runtime handles the agent loop, context management, and tool dispatch. The skill focuses on domain knowledge and investigation logic.

### `sre_oncall_triage_sdk/` — Standalone SDK Agent

The portfolio version. A from-scratch reimplementation using the Anthropic Messages API directly.

- **Owns the agent loop**: `agent.py` manages the `tool_use` protocol — LLM call → safety check → execute → trace → repeat
- **Safety as code**: `QueryGuard` (PromQL/LogQL rules) + `TierGate` (cluster classification) + `ScopeTracker` — all Python, not prompts
- **Pluggable backends**: `ToolBackend` Protocol for HTTP vs MCP; LLM client for Anthropic API vs OpenCode
- **Context management**: 3-tier strategy with explicit token budgets and automatic summarization at 70%
- **Execution tracing**: JSONL trace per investigation with per-tool-call latency, safety verdicts, branch decisions
- **Eval pipeline**: YAML test cases + 6-dimension scorer (routing, debug tree, verdict, sections, language, evidence)

See [`sre_oncall_triage_sdk/README.md`](sre_oncall_triage_sdk/README.md) and [`ARCHITECTURE.md`](sre_oncall_triage_sdk/ARCHITECTURE.md) for full details.

---

## Why Two Versions

| Dimension | Claude Code Skill | SDK Agent |
|-----------|------------------|-----------|
| Runtime | Claude Code session | Standalone Python process |
| Agent loop | Claude Code manages it | `agent.py` — you see every turn |
| Tool access | MCP servers | Direct HTTP (urllib, zero deps) |
| Safety enforcement | Shell hooks (`k8s-gate.sh`) | Python code (`query_guard.py`, `tier_gate.py`) |
| Context management | Claude Code auto-manages | Explicit 3-tier with token budget tracking |
| Observability | Hook-based JSONL audit | Code-level JSONL trace (per tool call) |
| Evaluation | Manual review | YAML cases + automated scorer |
| Knowledge base | 130+ files | Shared — same directory, path reference |

The Claude Code version is the daily driver (convenient, MCP integration just works). The SDK version exists to demonstrate understanding of what happens *inside* the agent loop — the protocol, the safety enforcement, the context economics.

---

## Shared Knowledge Base

Both agents use the same knowledge base (`sre_oncall_triage_agent/knowledge/`). The SDK agent references it via relative path — no symlinks, no duplication.

```
knowledge/
├── agent-routing-table.md         # Signal → cluster mapping (always in system prompt)
├── debug-trees/  (7 files)        # Executable decision trees
├── cases/        (~34 files)      # Incident postmortems
├── runbooks/     (~21 files)      # Procedures with #MANUAL gates
├── cards/        (~15 files)      # Fast-triage reference cards
├── patterns/     (4 files)        # Root cause models
├── checklists/   (3 files)        # Troubleshooting sequences
└── references/   (32 files)       # Architecture, commands, links
```

---

## LLM Backend: The OpenCode Workaround

The SDK agent was designed for the Anthropic Messages API (`tool_use` protocol). During development, without an API key, we attempted to use a local [OpenCode](https://github.com/opencode-ai/opencode) server as a drop-in LLM backend. This worked partially but surfaced fundamental architectural issues.

### What OpenCode Is

OpenCode is an agentic coding assistant (similar to Claude Code) exposed as an HTTP server. It has its own agent loop, tool set, system prompt, and context management.

### The Attempt

We built `llm/claude_code.py` (394 lines) — an adapter that mimics the `anthropic.Anthropic().messages.create()` interface but routes calls to OpenCode's HTTP API:

```
agent.py → OpenCodeLLM.messages.create()
             → POST /session/{id}/message (OpenCode server)
             → OpenCode internal agent processes the message
             → Poll GET /session/{id}/message for assistant response
             → Parse text → extract JSON tool calls → return Response object
```

To get structured output, we instructed OpenCode (via prompt) to respond in JSON:

```json
{"action": "tool_call", "tool_name": "vm_query_instant", "tool_input": {...}}
```

Then parsed it back out with regex on code fences and raw JSON.

### Problems Encountered

**1. Loss of tool_use protocol**

The Anthropic API returns structured `tool_use` blocks with `stop_reason: "tool_use"`. OpenCode returns natural language text. The adapter has to parse JSON out of prose — fragile and unreliable.

```
Expected (Anthropic API):
  stop_reason: "tool_use"
  content: [{type: "tool_use", name: "vm_query_instant", input: {...}, id: "call_1"}]

Got (OpenCode):
  "I'll query VictoriaMetrics to check if the pod is up..."
  (sometimes followed by a JSON block, sometimes not)
```

**2. Prompt/system-prompt interference**

Our system prompt (routing table + GCORF constraints + query safety rules) was sent as the first message. But OpenCode's internal agent prepends its own system prompt for coding tasks. Our instructions competed with or were overridden by OpenCode's built-in behavior.

**3. Tool schema registration ignored**

We registered 5 tool schemas (`vm_query_range`, `kubectl_read`, etc.) in the prompt. But OpenCode has its own tool set (file read, search, edit, bash). The LLM inside OpenCode saw both sets and often chose OpenCode's built-in tools instead of ours.

**4. Agent-inside-agent problem**

The fundamental issue: OpenCode is not an LLM endpoint — it's an agent. Sending a message to it triggers an internal loop that may:
- Rewrite the prompt
- Call its own tools before responding
- Summarize/transform the output

We were nesting one agent loop (ours) around another (OpenCode's), with neither having visibility into the other's state.

**5. Rate limits and provider instability**

OpenCode routes to upstream LLM providers. The Anthropic provider hit 429 rate limits. Switching to `gpt-5.2-codex/openai` worked but introduced yet another variable — different models follow the JSON output protocol with varying reliability.

### The Lesson

> **An agentic runtime is not a model API.** If you don't control the tool dispatch loop, you don't have an agent — you have a client of someone else's agent.

The SDK agent's value proposition is precisely that `agent.py` owns the loop: every tool call passes through `check_safety()` before execution, every result is recorded in the trace, and context budget is managed explicitly. Routing through OpenCode surrendered all of that.

### Resolution: Mock-Based Evaluation

Instead of fighting the OpenCode adapter, we built a proper evaluation pipeline:

```bash
# Run 2 test cases with mocked LLM + mocked tool responses
$ PYTHONPATH=src python -m sre_triage.eval.runner --cases eval/cases --mode mock

Running 2 test cases (mode=mock)

  [case-clickhouse-connection-refused-01] ClickHouse connection refused...
    → case-clickhouse-connection-refused-01:  90%  [RTVSLe]
  [case-false-p99-latency-01] P99 latency spike with normal error rate...
    → case-false-p99-latency-01:  90%  [RTVSLe]

============================================================
Results: 2/2 passed (≥80%)  |  avg score: 90%
```

The mock pipeline validates the entire agent loop — safety gates, tool dispatch, trace generation, scoring — without any LLM API call. `_build_mocks()` constructs a `MagicMock` that returns realistic `tool_use` responses following the Anthropic protocol exactly.

Score dimensions: **R**outing (20%) · debug **T**ree (20%) · **V**erdict (20%) · **S**ections (15%) · **L**anguage (15%) · **E**vidence (10%). Uppercase = pass, lowercase = fail.

---

## Running the Eval

```bash
cd agents/sre_oncall_triage_sdk

# Mock mode — no API key, no network
PYTHONPATH=src python -m sre_triage.eval.runner --cases eval/cases --mode mock

# Routing-only mode — tests signal extraction, no LLM
PYTHONPATH=src python -m sre_triage.eval.runner --cases eval/cases --mode routing

# Integration tests — safety, knowledge, tracing
PYTHONPATH=src python tests/test_integration.py

# Agent loop test — full 3-turn mock investigation
PYTHONPATH=src python tests/test_agent_loop.py
```

---

## Design Principles

These apply across both implementations:

1. **LLM is an unreliable component.** The system around it must be reliable. Safety checks are `if` statements, not system prompt instructions.

2. **Context is the bottleneck.** Not model capability — context quality and budget determine investigation quality. The 3-tier loading strategy (always / on-routing / on-demand) is the most important architectural decision.

3. **Observability is not optional.** Every tool call has a trace entry. Every safety check has a verdict. You can grep the JSONL and reconstruct exactly what the agent did and why.

4. **SRE and agent engineering are isomorphic.** RBAC → scope declaration. Blast radius → tier gate. Audit log → execution trace. SLI/SLO → eval scorer. The uncertainty comes from different sources (hardware vs. model), but the reliability patterns are the same.
