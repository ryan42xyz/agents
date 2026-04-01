"""Context window management — explicit token budget and summarization.

Three-tier strategy:
  T1: System prompt (always present, ~3k tokens)
  T2: Debug tree (loaded after routing, ~2-5k tokens)
  T3: On-demand knowledge retrieval (via lookup_knowledge tool)

Summarization triggers when cumulative tokens > 70% of window limit.
"""

from __future__ import annotations

from typing import Any

# Approximate context window for sonnet — conservative estimate
DEFAULT_CONTEXT_WINDOW = 200_000
SUMMARIZE_THRESHOLD = 0.7  # trigger at 70% utilization


class ContextManager:
    """Tracks token usage and triggers summarization when needed."""

    def __init__(self, context_window: int = DEFAULT_CONTEXT_WINDOW):
        self._context_window = context_window
        self._threshold = int(context_window * SUMMARIZE_THRESHOLD)

    def should_summarize(self, cumulative_input_tokens: int) -> bool:
        """Check if we should summarize to stay within budget."""
        return cumulative_input_tokens > self._threshold

    def summarize(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compress message history to reduce context usage.

        Strategy:
        - Keep the first user message (alert + instructions)
        - Keep the last 3 message pairs (most recent context)
        - Replace middle messages with a summary message
        """
        if len(messages) <= 6:
            return messages  # too short to summarize

        first_msg = messages[0]
        recent = messages[-6:]  # last 3 pairs (assistant + user)
        middle = messages[1:-6]

        # Build summary of middle messages
        summary_parts = ["## Investigation Progress So Far\n"]
        for msg in middle:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        summary_parts.append(
                            f"- Called {block['name']}({_truncate(str(block.get('input', {})), 80)})"
                        )
            elif role == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        status = "error" if block.get("is_error") else "ok"
                        preview = _truncate(str(block.get("content", "")), 100)
                        summary_parts.append(f"  → result ({status}): {preview}")

        summary_msg = {
            "role": "user",
            "content": "\n".join(summary_parts) + "\n\nContinue the investigation from here.",
        }

        return [first_msg, summary_msg] + recent


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s
