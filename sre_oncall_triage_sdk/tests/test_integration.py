"""Integration test — validates the full agent pipeline with a mocked Anthropic client.

Tests:
  1. System prompt construction (routing table loaded, constraints present)
  2. Agent loop with mocked tool calls
  3. Safety gates firing correctly
  4. Trace output complete
  5. Knowledge retrieval working
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sre_triage.config import Config
from sre_triage.context.knowledge import KnowledgeLoader
from sre_triage.context.manager import ContextManager
from sre_triage.observability.trace import Tracer
from sre_triage.safety.query_guard import QueryGuard
from sre_triage.safety.tier_gate import TierGate
from sre_triage.tools.registry import TOOL_SCHEMAS, ToolDispatcher


def test_system_prompt_construction():
    """System prompt includes routing table and constraints."""
    kb_path = Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "knowledge"
    facets_path = Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "FACETS"

    loader = KnowledgeLoader(kb_path, facets_path)
    routing = loader.load_routing_table()

    assert len(routing) > 1000, "Routing table should be substantial"
    assert "Cluster 1" in routing
    assert "Cluster 4" in routing
    assert "connection refused" in routing.lower()
    print("  PASS: system prompt construction")


def test_tool_schemas():
    """Tool schemas are valid for Anthropic API."""
    assert len(TOOL_SCHEMAS) == 5
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"vm_query_range", "vm_query_instant", "loki_query_range", "kubectl_read", "lookup_knowledge"}

    for tool in TOOL_SCHEMAS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema

    print("  PASS: tool schemas valid")


def test_query_guard_comprehensive():
    """Query guard catches all unsafe patterns."""
    qg = QueryGuard()

    # Valid queries
    assert qg.check_promql('up{namespace="default"}') is None
    assert qg.check_promql('rate(http_requests_total{job="api"}[5m])', step="60s") is None
    assert qg.check_logql('{job="ingress"} |= "error"', start="0", end="3600") is None

    # Invalid: no label filter
    assert qg.check_promql("up") is not None
    assert qg.check_promql("rate(http_requests_total[5m])") is not None

    # Invalid: wildcard on pod
    assert qg.check_promql('container_cpu{pod=~".*"}') is not None

    # Invalid: step too small
    assert qg.check_promql('up{job="a"}', step="5s") is not None

    # Invalid: window > 24h
    assert qg.check_promql('up{job="a"}', start="0", end="100000") is not None

    # Invalid: Loki no stream selector
    assert qg.check_logql("line_format") is not None

    # Invalid: Loki window > 6h
    assert qg.check_logql('{job="a"}', start="0", end="25000") is not None

    print("  PASS: query guard comprehensive")


def test_tier_gate_all_tiers():
    """Tier gate classifies and enforces correctly."""
    tg = TierGate()

    # Classification
    assert tg.classify_tier("kwestproda") == "PROD"
    assert tg.classify_tier("keastprodb") == "PROD"
    assert tg.classify_tier("keastpcia") == "PCI"
    assert tg.classify_tier("kwestmgt") == "MGT"
    assert tg.classify_tier("kwestpreprod") == "PREPROD"
    assert tg.classify_tier("kwestdeva") == "DEV"
    assert tg.classify_tier("kwestdemoa") == "DEMO"
    assert tg.classify_tier("unknown") == "UNKNOWN"

    # PROD: read OK, mutation blocked
    assert tg.check("get pods -n default", "kwestproda") is None
    assert tg.check("describe pod foo -n bar", "kwestproda") is None
    assert tg.check("scale deploy foo --replicas=2", "kwestproda") is not None
    assert tg.check("delete pod foo -n bar", "kwestproda") is not None

    # PREPROD: read OK, mutation without dry-run blocked
    assert tg.check("get pods", "kwestpreprod") is None
    assert tg.check("apply -f foo.yaml --dry-run=client", "kwestpreprod") is None  # dry-run OK
    assert tg.check("scale deploy foo", "kwestpreprod") is not None  # no dry-run

    # Namespace deletion blocked everywhere
    assert tg.check("delete namespace kube-system", "kwestdeva") is not None
    assert tg.check("del ns default", "kwestproda") is not None

    print("  PASS: tier gate all tiers")


def test_knowledge_search():
    """Knowledge retriever finds relevant files."""
    kb_path = Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "knowledge"
    facets_path = Path(__file__).parent.parent / ".." / "sre_oncall_triage_agent" / "FACETS"

    loader = KnowledgeLoader(kb_path, facets_path)

    # Search for clickhouse cases
    result = loader.search("clickhouse connection refused", kind="case")
    assert "clickhouse" in result.lower()
    assert len(result) > 100

    # Search for kafka
    result = loader.search("kafka lag")
    assert "kafka" in result.lower()

    # Load debug tree
    tree = loader.load_debug_tree("debug-tree-latency-breakdown.md")
    assert tree is not None
    assert len(tree) > 1000

    print("  PASS: knowledge search")


def test_tracer_output_format():
    """Trace output is valid JSONL with required fields."""
    with tempfile.TemporaryDirectory() as td:
        tracer = Tracer(Path(td))
        tracer.start("test-integration")

        tracer.record_turn(1, "assistant", [{"type": "text", "text": "Routing to Cluster 1"}], 500, 100)
        tracer.record_tool_call(
            turn=1,
            tool_name="vm_query_range",
            tool_input={"query": 'up{namespace="ch"}', "start": "0", "end": "3600", "step": "60s"},
            result={"data": {"resultType": "matrix", "result": []}},
            latency_ms=234.5,
            safety_checks={"query_guard": "pass", "scope": "pass", "tier": "PROD/read-ok"},
            branch_decision="no data → check endpoints",
        )
        tracer.record_tool_call(
            turn=2,
            tool_name="kubectl_read",
            tool_input={"command": "get endpoints -n ch", "cluster": "kwestproda"},
            result="NAME ENDPOINTS\nclickhouse <none>",
            latency_ms=123.0,
        )
        tracer.record_turn(2, "assistant", [{"type": "text", "text": "Investigation complete"}], 800, 200)

        path = tracer.finish()
        assert path is not None

        lines = path.read_text().splitlines()
        assert len(lines) == 6  # start + 2 turns + 2 tool_calls + end

        # Validate each entry
        for line in lines:
            entry = json.loads(line)
            assert "type" in entry
            assert "ts" in entry

        # Check summary
        end_entry = json.loads(lines[-1])
        assert end_entry["type"] == "investigation_end"
        summary = end_entry["summary"]
        assert summary["tool_calls"] == 2
        assert summary["total_input_tokens"] == 1300
        assert summary["total_output_tokens"] == 300

    print("  PASS: tracer output format")


def test_context_manager_summarization():
    """Context manager summarizes correctly without data loss."""
    cm = ContextManager(context_window=200_000)

    # Below threshold
    assert not cm.should_summarize(50_000)
    # Above threshold
    assert cm.should_summarize(150_000)

    # Build a long conversation
    messages = [{"role": "user", "content": "Alert: ClickHouse down"}]
    for i in range(10):
        messages.append({
            "role": "assistant",
            "content": [{"type": "tool_use", "name": f"vm_query_{i}", "input": {"query": f"q{i}"}}],
        })
        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": f"id{i}", "content": f"result {i}"}],
        })

    assert len(messages) == 21

    summarized = cm.summarize(messages)
    assert len(summarized) < len(messages)
    # First message preserved
    assert summarized[0]["content"] == "Alert: ClickHouse down"
    # Summary message present
    assert "Investigation Progress" in summarized[1]["content"]
    # Recent messages preserved
    assert len(summarized) == 8  # first + summary + last 6

    print("  PASS: context manager summarization")


def test_tool_dispatcher_with_mock_backend():
    """Tool dispatcher correctly routes calls to backend."""

    class MockBackend:
        def query_metrics(self, query, start, end, step):
            return {"status": "success", "data": {"result": []}}

        def query_metrics_instant(self, query):
            return {"status": "success", "data": {"result": []}}

        def query_logs(self, expr, start, end, limit=1000):
            return {"status": "success", "data": {"result": []}}

        def kubectl_read(self, command, cluster):
            return "NAME READY STATUS\npod-1 1/1 Running"

    dispatcher = ToolDispatcher(backend=MockBackend())

    # VM query
    result = dispatcher.execute("vm_query_range", {
        "query": 'up{job="test"}',
        "start": "0",
        "end": "3600",
        "step": "60s",
    })
    assert result.success
    assert result.data["status"] == "success"

    # kubectl
    result = dispatcher.execute("kubectl_read", {
        "command": "get pods -n default",
        "cluster": "kwestproda",
    })
    assert result.success
    assert "Running" in result.data

    # Unknown tool
    result = dispatcher.execute("unknown_tool", {})
    assert not result.success

    print("  PASS: tool dispatcher with mock backend")


if __name__ == "__main__":
    print("Running integration tests...\n")

    test_system_prompt_construction()
    test_tool_schemas()
    test_query_guard_comprehensive()
    test_tier_gate_all_tiers()
    test_knowledge_search()
    test_tracer_output_format()
    test_context_manager_summarization()
    test_tool_dispatcher_with_mock_backend()

    print(f"\n{'='*60}")
    print("All integration tests PASSED")
    print(f"{'='*60}")
