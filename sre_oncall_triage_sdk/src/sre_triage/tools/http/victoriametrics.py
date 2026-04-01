"""Direct HTTP backend for VictoriaMetrics and Loki APIs.

Adapted from sre_oncall_triage_agent/tools/vm_lookup.py pattern.
Uses stdlib urllib only — zero external dependencies.
"""

from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from typing import Any


class HttpVictoriaMetrics:
    """Combined HTTP backend for VictoriaMetrics, Loki, and kubectl.

    Implements the ToolBackend protocol.
    """

    def __init__(
        self,
        base_url: str,
        loki_url: str = "",
        loki_org_id: str = "prod",
        timeout_s: float = 15.0,
    ):
        self._vm_base_url = base_url.rstrip("/")
        self._loki_url = loki_url.rstrip("/")
        self._loki_org_id = loki_org_id
        self._timeout_s = timeout_s

    def query_metrics(
        self,
        query: str,
        start: str,
        end: str,
        step: str,
    ) -> dict[str, Any]:
        """PromQL range query against VictoriaMetrics."""
        params = urllib.parse.urlencode({
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        })
        url = f"{self._vm_base_url}/prometheus/api/v1/query_range?{params}"
        return self._http_get(url)

    def query_metrics_instant(self, query: str) -> dict[str, Any]:
        """PromQL instant query against VictoriaMetrics."""
        params = urllib.parse.urlencode({"query": query})
        url = f"{self._vm_base_url}/prometheus/api/v1/query?{params}"
        return self._http_get(url)

    def query_logs(
        self,
        expr: str,
        start: str,
        end: str,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """LogQL range query against Loki."""
        if not self._loki_url:
            raise RuntimeError("LOKI_URL not configured")

        params = urllib.parse.urlencode({
            "query": expr,
            "start": start,
            "end": end,
            "limit": str(limit),
            "direction": "backward",
        })
        url = f"{self._loki_url}/loki/api/v1/query_range?{params}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "sre-triage-agent/0.1",
        }
        if self._loki_org_id:
            headers["X-Scope-OrgID"] = self._loki_org_id

        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
            body = response.read().decode("utf-8")

        payload = json.loads(body)
        if payload.get("status") != "success":
            raise RuntimeError(f"Loki query failed: {payload.get('error', 'unknown')}")
        return payload

    def kubectl_read(self, command: str, cluster: str) -> str:
        """Execute a read-only kubectl command via subprocess.

        Only allows: get, describe, logs, top, auth.
        The cluster alias is used as the kubectl command prefix.
        """
        # Validate: read-only commands only
        parts = command.strip().split()
        if not parts:
            raise RuntimeError("Empty kubectl command")

        subcmd = parts[0]
        allowed = {"get", "describe", "logs", "top", "auth"}
        if subcmd not in allowed:
            raise RuntimeError(
                f"kubectl subcommand '{subcmd}' not allowed. Allowed: {', '.join(sorted(allowed))}"
            )

        # Build the full command: cluster_alias + command
        full_cmd = f"{cluster} {command}"

        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"kubectl failed (exit {result.returncode}): {stderr[:500]}")

        return result.stdout

    def _http_get(self, url: str) -> dict[str, Any]:
        """Generic HTTP GET with JSON response parsing."""
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "sre-triage-agent/0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
            body = response.read().decode("utf-8")

        payload = json.loads(body)
        if payload.get("status") != "success":
            raise RuntimeError(f"Query failed: {payload.get('error', 'unknown')}")
        return payload
