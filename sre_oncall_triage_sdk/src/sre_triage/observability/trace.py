"""Execution trace — JSONL structured log of every agent turn and tool call.

Each investigation produces a trace file with:
  - Turn-level entries (API call, tokens, stop reason)
  - Tool-level entries (input, output, latency, safety checks, branch decisions)

Format is designed to be OTel-compatible for future migration.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Tracer:
    """Records structured execution traces to JSONL files."""

    def __init__(self, trace_dir: Path):
        self._trace_dir = trace_dir
        self._entries: list[dict[str, Any]] = []
        self._investigation_id: str = ""
        self._tool_calls: list[dict[str, Any]] = []

    def start(self, investigation_id: str) -> None:
        """Start a new trace for an investigation."""
        self._investigation_id = investigation_id
        self._entries = []
        self._tool_calls = []
        self._entries.append({
            "type": "investigation_start",
            "investigation_id": investigation_id,
            "ts": _now_iso(),
        })

    def record_turn(
        self,
        turn: int,
        role: str,
        content: list[dict] | str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record an API turn (assistant response)."""
        # Summarize content for trace (don't store full text)
        content_summary = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        content_summary.append(f"text({len(text)} chars)")
                    elif block.get("type") == "tool_use":
                        content_summary.append(f"tool_use({block.get('name', '?')})")
        else:
            content_summary.append(f"text({len(str(content))} chars)")

        self._entries.append({
            "type": "turn",
            "turn": turn,
            "role": role,
            "content_summary": content_summary,
            "tokens_in": input_tokens,
            "tokens_out": output_tokens,
            "ts": _now_iso(),
        })

    def record_tool_call(
        self,
        turn: int,
        tool_name: str,
        tool_input: dict[str, Any],
        result: Any = None,
        error: str | None = None,
        latency_ms: float = 0.0,
        safety_checks: dict[str, str] | None = None,
        branch_decision: str | None = None,
    ) -> None:
        """Record a single tool call with its result and metadata."""
        entry = {
            "type": "tool_call",
            "turn": turn,
            "tool": tool_name,
            "input": _truncate_dict(tool_input, max_value_len=200),
            "output_preview": _truncate_str(json.dumps(result) if result else str(error), 300),
            "success": error is None,
            "error": error,
            "latency_ms": round(latency_ms, 1),
            "safety": safety_checks or {},
            "branch": branch_decision,
            "ts": _now_iso(),
        }
        self._entries.append(entry)
        self._tool_calls.append(entry)

    def get_log(self) -> list[dict[str, Any]]:
        """Return tool calls for the investigation log table."""
        return list(self._tool_calls)

    def finish(self) -> Path | None:
        """Write the trace to a JSONL file and return the path."""
        if not self._entries:
            return None

        # Add summary entry
        tool_call_count = len(self._tool_calls)
        total_latency = sum(tc.get("latency_ms", 0) for tc in self._tool_calls)
        total_input = sum(
            e.get("tokens_in", 0) for e in self._entries if e.get("type") == "turn"
        )
        total_output = sum(
            e.get("tokens_out", 0) for e in self._entries if e.get("type") == "turn"
        )

        self._entries.append({
            "type": "investigation_end",
            "investigation_id": self._investigation_id,
            "ts": _now_iso(),
            "summary": {
                "turns": max(
                    (e.get("turn", 0) for e in self._entries if e.get("type") == "turn"),
                    default=0,
                ),
                "tool_calls": tool_call_count,
                "total_tool_latency_ms": round(total_latency, 1),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "errors": sum(1 for tc in self._tool_calls if not tc.get("success")),
            },
        })

        # Write JSONL
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        path = self._trace_dir / f"trace-{self._investigation_id}.jsonl"
        with open(path, "w") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, default=str) + "\n")

        return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_str(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _truncate_dict(d: dict, max_value_len: int = 200) -> dict:
    """Truncate long string values in a dict for trace storage."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > max_value_len:
            result[k] = v[:max_value_len] + "..."
        else:
            result[k] = v
    return result
