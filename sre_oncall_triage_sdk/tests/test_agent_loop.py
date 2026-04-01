"""Agent loop test — validates the full investigate() flow with mocked Anthropic API.

Simulates a 3-turn investigation:
  Turn 1: LLM routes to Cluster 1, requests vm_query_range
  Turn 2: LLM sees empty metrics, requests kubectl_read
  Turn 3: LLM produces final investigation report
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sre_triage.config import Config
from sre_triage.agent import TriageAgent


def _make_text_block(text: str):
    """Create a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_id: str, name: str, input_data: dict):
    """Create a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _make_response(content_blocks, stop_reason="end_turn", input_tokens=500, output_tokens=200):
    """Create a mock API response."""
    resp = MagicMock()
    resp.content = content_blocks
    resp.stop_reason = stop_reason
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def test_full_investigation_loop():
    """Full 3-turn agent loop with mocked API and backend."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        config = Config(
            api_key="sk-test-mock",
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            max_turns=10,
            tool_backend="http",
            vm_base_url="http://mock-vm:8428",
            loki_url="http://mock-loki:3100",
            knowledge_base_path=Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "knowledge",
            facets_path=Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "FACETS",
            output_dir=td_path / "output",
            trace_dir=td_path / "traces",
        )

        # Mock the Anthropic client responses
        # Turn 1: LLM requests vm_query_range
        turn1_response = _make_response(
            content_blocks=[
                _make_text_block("Routing to Cluster 1 (connection refused). Checking metrics."),
                _make_tool_use_block("call_1", "vm_query_range", {
                    "query": 'kube_pod_info{namespace="clickhouse"}',
                    "start": "1711900000",
                    "end": "1711903600",
                    "step": "60s",
                }),
            ],
            stop_reason="tool_use",
            input_tokens=3000,
            output_tokens=150,
        )

        # Turn 2: LLM sees empty result, requests kubectl
        turn2_response = _make_response(
            content_blocks=[
                _make_text_block("No pod info found via metrics. Checking endpoints directly."),
                _make_tool_use_block("call_2", "kubectl_read", {
                    "command": "get endpoints clickhouse -n clickhouse",
                    "cluster": "kwestproda",
                }),
            ],
            stop_reason="tool_use",
            input_tokens=4000,
            output_tokens=100,
        )

        # Turn 3: Final report
        final_report = """## 1. Investigation Scope

```yaml
cluster: aws-uswest2-prod-a
services: [clickhouse]
namespaces: [clickhouse]
tools: [vm_query_range, kubectl_read]
time_window: "2024-03-31 14:00 - 15:00 UTC"
out_of_scope: []
```

## 2. Slack Response

**Impact**: ClickHouse service on aws-uswest2-prod-a is possibly unreachable on port 9000.
**Status**: Investigating — endpoints appear empty, consistent with pods not running.
**Immediate Action**: Checking pod status and recent events.
**Next Steps**: Verify pod scheduling, check for recent deployments.

## 3. Internal Notes

**Triage Result**: Cluster 1 — Routing/Ingress
**Conclusion**: Endpoints are empty, likely indicating pods are not running or not ready.
**Event Type**: service_unavailable
**Verdict**: NEEDS_ATTENTION
**Confidence**: medium
**Evidence Chain**: [vm_query_range returned empty, kubectl endpoints show <none>]
**Uncertainty Note**: Root cause not yet determined — could be scheduling, crash, or deployment issue.

## 4. Extracted Signals

- alertname: ClickHouse connection refused
- cluster: aws-uswest2-prod-a
- service: clickhouse
- port: 9000

## 5. Links

Ready: (none — no dashboard links resolved)

## 6. Investigation Log

| Step | Tool | Query | Result | Interpretation | Branch |
|------|------|-------|--------|----------------|--------|
| 1 | vm_query_range | kube_pod_info{namespace="clickhouse"} | empty | No pods found via metrics | → check endpoints |
| 2 | kubectl_read | get endpoints clickhouse -n clickhouse | <none> | Endpoints empty | → NEEDS_ATTENTION |
"""

        turn3_response = _make_response(
            content_blocks=[_make_text_block(final_report)],
            stop_reason="end_turn",
            input_tokens=5000,
            output_tokens=500,
        )

        # Patch Anthropic client and HTTP backend
        with patch("sre_triage.agent.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = [
                turn1_response,
                turn2_response,
                turn3_response,
            ]

            # Patch the HTTP backend
            with patch("sre_triage.tools.http.victoriametrics.HttpVictoriaMetrics") as MockHTTP:
                mock_backend = MagicMock()
                mock_backend.query_metrics.return_value = {
                    "status": "success",
                    "data": {"resultType": "matrix", "result": []},
                }
                mock_backend.kubectl_read.return_value = "NAME       ENDPOINTS\nclickhouse <none>"
                MockHTTP.return_value = mock_backend

                agent = TriageAgent(config)
                result = agent.investigate(
                    "[FIRING] ClickHouse connection refused on port 9000\n"
                    "cluster: aws-uswest2-prod-a\n"
                    "service: clickhouse\n"
                    "error: dial tcp 10.0.1.42:9000: connect: connection refused"
                )

        # Verify results
        assert result.turns == 3, f"Expected 3 turns, got {result.turns}"
        assert result.total_input_tokens == 12000  # 3000 + 4000 + 5000
        assert result.total_output_tokens == 750   # 150 + 100 + 500
        assert "NEEDS_ATTENTION" in result.final_response
        assert "Investigation Scope" in result.final_response

        # Verify output file
        assert result.output_path is not None
        assert result.output_path.exists()
        output_content = result.output_path.read_text()
        assert "Slack Response" in output_content

        # Verify trace file
        assert result.trace_path is not None
        assert result.trace_path.exists()
        trace_lines = result.trace_path.read_text().splitlines()

        # Should have: start + 3 turns + 2 tool_calls + end = 7 entries
        types = [json.loads(line)["type"] for line in trace_lines]
        assert "investigation_start" in types
        assert "investigation_end" in types
        assert types.count("tool_call") == 2
        assert types.count("turn") == 3

        # Check trace summary
        end_entry = json.loads(trace_lines[-1])
        assert end_entry["summary"]["tool_calls"] == 2
        assert end_entry["summary"]["total_input_tokens"] == 12000

        print("  PASS: full investigation loop (3 turns, 2 tool calls)")
        print(f"    Output: {result.output_path}")
        print(f"    Trace: {result.trace_path}")
        print(f"    Tokens: {result.total_input_tokens}in/{result.total_output_tokens}out")


if __name__ == "__main__":
    print("Running agent loop tests...\n")
    test_full_investigation_loop()
    print(f"\n{'='*60}")
    print("All agent loop tests PASSED")
    print(f"{'='*60}")
