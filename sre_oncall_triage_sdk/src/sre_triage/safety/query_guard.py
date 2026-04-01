"""Query safety guard — validates PromQL and LogQL queries before execution.

Enforces rules from SKILL.md:
  - Every PromQL: >= 1 label filter
  - query_range step >= 30s, window <= 24h
  - Every LogQL: >= 1 stream selector
  - No regex wildcard on high-cardinality labels
"""

from __future__ import annotations

import re
from datetime import datetime


# High-cardinality labels that should not use =~ ".*"
HIGH_CARDINALITY_LABELS = {"pod", "instance", "container", "container_id", "pod_ip"}


class QueryGuard:
    """Validates metric and log queries against safety rules."""

    def check_promql(
        self,
        query: str,
        step: str = "",
        start: str = "",
        end: str = "",
    ) -> str | None:
        """Check a PromQL query. Returns error message if invalid, None if OK."""
        # Rule 1: at least one label filter
        if not _has_label_filter(query):
            return f"Query rejected: no label filter found. Add at least one label filter (namespace, job, service). Query: {query[:100]}"

        # Rule 2: no wildcard regex on high-cardinality labels
        for label in HIGH_CARDINALITY_LABELS:
            if re.search(rf'{label}\s*=~\s*"\.?\*"', query):
                return f"Query rejected: wildcard regex on high-cardinality label '{label}'. Use a specific filter."

        # Rule 3: step >= 30s (for range queries)
        if step:
            step_seconds = _parse_duration(step)
            if step_seconds is not None and step_seconds < 30:
                return f"Query rejected: step={step} is below minimum 30s."

        # Rule 4: time window <= 24h
        if start and end:
            window_seconds = _time_window_seconds(start, end)
            if window_seconds is not None and window_seconds > 86400:
                return f"Query rejected: time window ({window_seconds}s) exceeds 24h limit."

        return None

    def check_logql(
        self,
        expr: str,
        start: str = "",
        end: str = "",
    ) -> str | None:
        """Check a LogQL query. Returns error message if invalid, None if OK."""
        # Rule 1: at least one stream selector
        if not re.search(r'\{[^}]+\}', expr):
            return f"Query rejected: no stream selector found. Add at least one {{label=\"value\"}}. Expr: {expr[:100]}"

        # Rule 2: time window <= 6h
        if start and end:
            window_seconds = _time_window_seconds(start, end)
            if window_seconds is not None and window_seconds > 21600:
                return f"Query rejected: Loki time window ({window_seconds}s) exceeds 6h limit."

        return None


def _has_label_filter(query: str) -> bool:
    """Check if a PromQL query contains at least one label filter."""
    # Look for {label="value"} or {label=~"pattern"} or {label!="value"}
    return bool(re.search(r'\{[^}]*\w+\s*[=!~]+\s*"[^"]*"', query))


def _parse_duration(s: str) -> int | None:
    """Parse a duration string like '30s', '5m', '1h' to seconds."""
    match = re.match(r'^(\d+)(s|m|h|d)$', s.strip())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def _time_window_seconds(start: str, end: str) -> int | None:
    """Calculate the time window in seconds between start and end."""
    try:
        # Try Unix timestamps first
        s = float(start)
        e = float(end)
        return int(e - s)
    except (ValueError, TypeError):
        pass

    # Try RFC3339
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return int((e - s).total_seconds())
    except (ValueError, TypeError):
        return None
