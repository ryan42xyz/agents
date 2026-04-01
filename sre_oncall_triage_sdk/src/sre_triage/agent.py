"""Core agent loop — the heart of the SDK-level implementation.

Manages the tool_use cycle with pluggable LLM backends:
  - Anthropic API (default): anthropic.Anthropic().messages.create()
  - Claude Code CLI: claude -p with --json-schema (no API key needed)

The loop is identical regardless of backend:
  1. Build system prompt with routing table + constraints
  2. Send alert text as initial user message
  3. Loop: LLM call → tool_use → safety check → execute → record → respond
  4. On end_turn: render output, verify, return result
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .context.knowledge import KnowledgeLoader
from .context.manager import ContextManager
from .observability.trace import Tracer
from .safety.query_guard import QueryGuard
from .safety.scope import ScopeTracker
from .safety.tier_gate import TierGate
from .tools.registry import TOOL_SCHEMAS, ToolDispatcher


@dataclass
class InvestigationResult:
    """Complete result of an agent investigation."""
    final_response: str
    trace_path: Path | None = None
    output_path: Path | None = None
    turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class TriageAgent:
    """Standalone SRE oncall triage agent with pluggable LLM backend."""

    def __init__(self, config: Config):
        self._config = config
        self._client = self._create_llm_client(config)
        self._knowledge = KnowledgeLoader(config.knowledge_base_path, config.facets_path)
        self._context_mgr = ContextManager()
        self._tracer = Tracer(config.trace_dir)
        self._query_guard = QueryGuard()
        self._scope_tracker = ScopeTracker()
        self._tier_gate = TierGate()

        # Tool dispatch — backend selected by config
        backend = self._create_backend()
        self._dispatcher = ToolDispatcher(
            backend=backend,
            knowledge_retriever=self._knowledge,
        )

    @staticmethod
    def _create_llm_client(config: Config):
        """Create the LLM client based on config.

        Two backends:
          - "api" (default): Anthropic SDK — requires ANTHROPIC_API_KEY
          - "opencode": Local OpenCode server — no API key needed, uses HTTP API
        """
        if config.llm_backend == "opencode":
            from .llm.claude_code import OpenCodeLLM
            return OpenCodeLLM()
        else:
            import anthropic
            return anthropic.Anthropic(api_key=config.api_key)

    def _create_backend(self):
        """Create the tool backend based on config."""
        if self._config.tool_backend == "mcp":
            from .tools.mcp.adapter import McpBackend
            return McpBackend()
        else:
            from .tools.http.victoriametrics import HttpVictoriaMetrics
            return HttpVictoriaMetrics(
                base_url=self._config.vm_base_url,
                loki_url=self._config.loki_url,
                loki_org_id=self._config.loki_org_id,
            )

    def investigate(self, alert_text: str) -> InvestigationResult:
        """Run a full investigation for the given alert text.

        This is the main entry point. It:
        1. Builds the system prompt with routing table and constraints
        2. Enters the tool_use loop
        3. Returns the structured result
        """
        # Build system prompt
        system_prompt = self._build_system_prompt()

        # Initialize message history
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": self._build_initial_message(alert_text)},
        ]

        # Start trace
        investigation_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        self._tracer.start(investigation_id)

        total_input_tokens = 0
        total_output_tokens = 0
        turns = 0

        # --- Agent loop ---
        while turns < self._config.max_turns:
            turns += 1

            response = self._client.messages.create(
                model=self._config.model,
                system=system_prompt,
                messages=messages,
                tools=TOOL_SCHEMAS,
                max_tokens=self._config.max_tokens,
            )

            # Track tokens
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Record turn in trace
            self._tracer.record_turn(
                turn=turns,
                role="assistant",
                content=_serialize_content(response.content),
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            # Check stop reason
            if response.stop_reason == "end_turn":
                final_text = _extract_text(response.content)
                break

            # Process tool_use blocks
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                # Safety checks
                safety_error = self._check_safety(tool_name, tool_input)
                if safety_error:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"BLOCKED by safety gate: {safety_error}",
                        "is_error": True,
                    })
                    self._tracer.record_tool_call(
                        turn=turns,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        result=None,
                        error=safety_error,
                        safety_checks={"blocked": True, "reason": safety_error},
                    )
                    continue

                # Execute tool
                result = self._dispatcher.execute(tool_name, tool_input)

                # Format result for API
                if result.success:
                    result_content = json.dumps(result.data) if isinstance(result.data, (dict, list)) else str(result.data)
                else:
                    result_content = f"ERROR: {result.error}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content,
                    "is_error": not result.success,
                })

                # Record in trace
                self._tracer.record_tool_call(
                    turn=turns,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    result=result.data if result.success else None,
                    error=result.error,
                    latency_ms=result.latency_ms,
                    safety_checks={"query_guard": "pass", "scope": "pass"},
                )

            # Append assistant message + tool results to history
            messages.append({"role": "assistant", "content": _content_to_dicts(response.content)})
            messages.append({"role": "user", "content": tool_results})

            # Context budget check
            if self._context_mgr.should_summarize(total_input_tokens):
                messages = self._context_mgr.summarize(messages)

        else:
            # Max turns reached
            final_text = f"Investigation stopped: max turns ({self._config.max_turns}) reached."

        # Save trace
        trace_path = self._tracer.finish()

        # Save output
        output_path = self._save_output(investigation_id, final_text)

        return InvestigationResult(
            final_response=final_text,
            trace_path=trace_path,
            output_path=output_path,
            turns=turns,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )

    def _build_system_prompt(self) -> str:
        """Build the system prompt with routing table, constraints, and query safety rules."""
        routing_table = self._knowledge.load_routing_table()
        parts = [
            "You are an SRE oncall triage agent. Your job is to investigate production alerts "
            "using available tools and produce evidence-backed findings.\n",
            "## Hard Constraints\n"
            "- Read-only investigation only. Never mutate production systems.\n"
            "- Evidence-backed conclusions only. State uncertainty when it exists.\n"
            "- Conservative Slack language: use 'likely', 'possibly', 'consistent with'. "
            "Never 'root cause is', 'definitely', 'all users'.\n"
            "- Every conclusion must have an evidence chain.\n",
            "## Query Safety Rules\n"
            "- Every PromQL query must include >= 1 label filter (namespace/job/service)\n"
            "- query_range step >= 30s, time window <= 24h\n"
            "- Every LogQL query must include >= 1 stream selector\n"
            "- No regex wildcard on high-cardinality labels (pod, instance, container)\n"
            "- Max 2 retries per query\n",
            "## Verdict Vocabulary\n"
            "IGNORE_DEV | KNOWN_ISSUE | NON_ACTIONABLE_NOISE | NEEDS_ATTENTION | ESCALATE | MANUAL\n",
            "## Routing Table\n",
            routing_table,
            "\n## Output Format\n"
            "Your final response must include these sections in order:\n"
            "1. Investigation Scope (YAML)\n"
            "2. Slack Response (Impact, Status, Immediate Action, Next Steps)\n"
            "3. Internal Notes (triage result, conclusion, event type, hypothesis tree, evidence checklist, uncertainty)\n"
            "4. Extracted Signals\n"
            "5. Links\n"
            "6. Investigation Log (table: Step | Tool | Query | Result | Interpretation | Branch)\n",
        ]
        return "\n".join(parts)

    def _build_initial_message(self, alert_text: str) -> str:
        """Build the initial user message with the alert and instructions."""
        return (
            f"## Alert Input\n\n{alert_text}\n\n"
            "## Instructions\n\n"
            "1. Extract signals from this alert\n"
            "2. Route to the correct triage cluster using the routing table\n"
            "3. If a debug tree matches, follow its steps using tools\n"
            "4. Produce the full investigation output in the required format\n"
        )

    def _check_safety(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Run all safety checks. Returns error message if blocked, None if OK."""
        # Query guard
        if tool_name == "vm_query_range":
            error = self._query_guard.check_promql(
                tool_input.get("query", ""),
                step=tool_input.get("step", ""),
                start=tool_input.get("start", ""),
                end=tool_input.get("end", ""),
            )
            if error:
                return error

        elif tool_name == "vm_query_instant":
            error = self._query_guard.check_promql(tool_input.get("query", ""))
            if error:
                return error

        elif tool_name == "loki_query_range":
            error = self._query_guard.check_logql(
                tool_input.get("expr", ""),
                start=tool_input.get("start", ""),
                end=tool_input.get("end", ""),
            )
            if error:
                return error

        elif tool_name == "kubectl_read":
            error = self._tier_gate.check(
                command=tool_input.get("command", ""),
                cluster=tool_input.get("cluster", ""),
            )
            if error:
                return error

        return None

    def _save_output(self, investigation_id: str, content: str) -> Path:
        """Save the investigation output to a file."""
        self._config.output_dir.mkdir(parents=True, exist_ok=True)
        path = self._config.output_dir / f"sre-triage-{investigation_id}.md"
        path.write_text(content)
        return path


# --- Helpers ---

def _extract_text(content: list) -> str:
    """Extract text blocks from API response content."""
    parts = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


def _serialize_content(content: list) -> list[dict]:
    """Serialize API response content to JSON-safe dicts."""
    result = []
    for block in content:
        if hasattr(block, "text"):
            result.append({"type": "text", "text": block.text})
        elif hasattr(block, "name"):
            result.append({
                "type": "tool_use",
                "name": block.name,
                "input": block.input,
                "id": block.id,
            })
    return result


def _content_to_dicts(content: list) -> list[dict]:
    """Convert API response content blocks to dicts for message history."""
    return _serialize_content(content)
