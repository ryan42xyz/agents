"""Tool schema registry and dispatch for Anthropic Messages API.

Defines tool schemas in Anthropic format and dispatches tool_use calls
to the configured backend (HTTP or MCP).
"""

from __future__ import annotations

import time
from typing import Any

from .base import ToolBackend, ToolResult


# --- Anthropic tool schemas ---

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "vm_query_range",
        "description": (
            "Query VictoriaMetrics with PromQL over a time range. "
            "Every query MUST include at least one label filter (namespace, job, or service). "
            "Step must be >= 30s. Time window must be <= 24h."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL expression with at least one label filter",
                },
                "start": {
                    "type": "string",
                    "description": "Start time (RFC3339 or Unix timestamp)",
                },
                "end": {
                    "type": "string",
                    "description": "End time (RFC3339 or Unix timestamp)",
                },
                "step": {
                    "type": "string",
                    "description": "Query step interval (e.g., '60s', '5m'). Minimum 30s.",
                },
            },
            "required": ["query", "start", "end", "step"],
        },
    },
    {
        "name": "vm_query_instant",
        "description": (
            "Execute an instant PromQL query against VictoriaMetrics. "
            "Every query MUST include at least one label filter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL expression with at least one label filter",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "loki_query_range",
        "description": (
            "Query Loki logs with LogQL over a time range. "
            "Every query MUST include at least one stream selector. "
            "Time window must be <= 6h."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expr": {
                    "type": "string",
                    "description": "LogQL expression with at least one stream selector",
                },
                "start": {
                    "type": "string",
                    "description": "Start time (RFC3339 or Unix timestamp)",
                },
                "end": {
                    "type": "string",
                    "description": "End time (RFC3339 or Unix timestamp)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max log lines to return (default 1000)",
                    "default": 1000,
                },
            },
            "required": ["expr", "start", "end"],
        },
    },
    {
        "name": "kubectl_read",
        "description": (
            "Execute a read-only kubectl command (get, describe, logs only). "
            "Specify the cluster alias and the full command. "
            "Mutations are blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Full kubectl command (e.g., 'get pods -n default')",
                },
                "cluster": {
                    "type": "string",
                    "description": "Cluster alias (e.g., 'kwestproda', 'keastprodb')",
                },
            },
            "required": ["command", "cluster"],
        },
    },
    {
        "name": "lookup_knowledge",
        "description": (
            "Search the oncall knowledge base by tags or kind. "
            "Returns matching file contents. Use for cases, runbooks, patterns, references."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms (e.g., 'clickhouse connection refused', 'kafka lag')",
                },
                "kind": {
                    "type": "string",
                    "description": "Filter by kind: case, runbook, card, pattern, reference, checklist",
                    "enum": ["case", "runbook", "card", "pattern", "reference", "checklist"],
                },
            },
            "required": ["query"],
        },
    },
]


class ToolDispatcher:
    """Dispatches Anthropic tool_use calls to the configured backend."""

    def __init__(self, backend: ToolBackend, knowledge_retriever=None):
        self._backend = backend
        self._knowledge_retriever = knowledge_retriever

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a tool call and return a standardized result."""
        start = time.monotonic()
        try:
            if tool_name == "vm_query_range":
                data = self._backend.query_metrics(
                    query=tool_input["query"],
                    start=tool_input["start"],
                    end=tool_input["end"],
                    step=tool_input["step"],
                )
            elif tool_name == "vm_query_instant":
                data = self._backend.query_metrics_instant(
                    query=tool_input["query"],
                )
            elif tool_name == "loki_query_range":
                data = self._backend.query_logs(
                    expr=tool_input["expr"],
                    start=tool_input["start"],
                    end=tool_input["end"],
                    limit=tool_input.get("limit", 1000),
                )
            elif tool_name == "kubectl_read":
                data = self._backend.kubectl_read(
                    command=tool_input["command"],
                    cluster=tool_input["cluster"],
                )
            elif tool_name == "lookup_knowledge":
                if self._knowledge_retriever is None:
                    return ToolResult(
                        tool_name=tool_name,
                        success=False,
                        data=None,
                        error="Knowledge retriever not configured",
                    )
                data = self._knowledge_retriever.search(
                    query=tool_input["query"],
                    kind=tool_input.get("kind"),
                )
            else:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    data=None,
                    error=f"Unknown tool: {tool_name}",
                )

            elapsed = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=True,
                data=data,
                latency_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=str(e),
                latency_ms=elapsed,
            )
