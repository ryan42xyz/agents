"""MCP client adapter — alternative backend using existing MCP servers.

Implements the same ToolBackend protocol as the HTTP backend,
but delegates to MCP servers instead of making direct HTTP calls.

Requires: pip install 'sre-triage-agent[mcp]'
"""

from __future__ import annotations

from typing import Any


class McpBackend:
    """MCP-based tool backend.

    Connects to running MCP servers (VictoriaMetrics, Grafana)
    and translates ToolBackend calls to MCP tool calls.

    TODO: Implement when MCP client library is available.
    """

    def __init__(self):
        raise NotImplementedError(
            "MCP backend not yet implemented. Use TOOL_BACKEND=http (default). "
            "MCP adapter is planned for Phase 2."
        )

    def query_metrics(
        self, query: str, start: str, end: str, step: str
    ) -> dict[str, Any]:
        # Will call: mcp__victoriametrics__query_range
        raise NotImplementedError

    def query_metrics_instant(self, query: str) -> dict[str, Any]:
        # Will call: mcp__victoriametrics__query
        raise NotImplementedError

    def query_logs(
        self, expr: str, start: str, end: str, limit: int = 1000
    ) -> dict[str, Any]:
        # Will call: mcp__grafana__query_loki_logs
        raise NotImplementedError

    def kubectl_read(self, command: str, cluster: str) -> str:
        # MCP doesn't have a kubectl server — fall back to subprocess
        raise NotImplementedError
