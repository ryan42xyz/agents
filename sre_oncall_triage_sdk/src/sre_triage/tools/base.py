"""Tool backend abstraction — the key architectural boundary.

Two implementations:
  - http/  : Direct HTTP calls to VictoriaMetrics/Loki APIs (default)
  - mcp/   : MCP client adapter connecting to existing MCP servers (optional)

Switch via TOOL_BACKEND=http|mcp in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ToolBackend(Protocol):
    """Abstract interface for data source access.

    Both HTTP and MCP backends implement this protocol.
    The agent loop only depends on this interface.
    """

    def query_metrics(
        self,
        query: str,
        start: str,
        end: str,
        step: str,
    ) -> dict[str, Any]:
        """Execute a PromQL/MetricsQL query_range against VictoriaMetrics."""
        ...

    def query_metrics_instant(
        self,
        query: str,
    ) -> dict[str, Any]:
        """Execute an instant PromQL query."""
        ...

    def query_logs(
        self,
        expr: str,
        start: str,
        end: str,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """Execute a LogQL query_range against Loki."""
        ...

    def kubectl_read(
        self,
        command: str,
        cluster: str,
    ) -> str:
        """Execute a read-only kubectl command. Returns stdout."""
        ...


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    tool_name: str
    success: bool
    data: Any
    error: str | None = None
    latency_ms: float = 0.0
