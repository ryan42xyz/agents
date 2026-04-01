"""OpenCode server backend — uses local OpenCode HTTP API as LLM.

Pure HTTP API: create session → send message → get response.
No internal agent loop interference. Reliable structured output via json_schema.

Implements the same interface as anthropic.Anthropic().messages so the
agent loop doesn't need to change — just swap the client.

Usage:
    from sre_triage.llm.claude_code import OpenCodeLLM
    client = OpenCodeLLM()
    response = client.messages.create(system=..., messages=..., tools=...)
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import urllib.parse
import urllib.request


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class Response:
    """Mimics anthropic.types.Message interface."""
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


class OpenCodeLLM:
    """LLM client using local OpenCode server as backend.

    Drop-in replacement for anthropic.Anthropic() — the agent loop calls
    client.messages.create() which routes to OpenCode HTTP API.

    Architecture:
      agent.py → OpenCodeLLM.messages.create()
                   → POST /session/{id}/message (OpenCode server)
                   → OpenCode forwards to Anthropic/other LLM providers
                   → Parse response → Return Response object
    """

    def __init__(
        self,
        base_url: str | None = None,
        password: str | None = None,
        username: str = "opencode",
        model_id: str = "claude-sonnet-4-5-20250929",
        provider_id: str = "anthropic",
    ):
        # Load from env
        self._base_url = (base_url or os.environ.get("OPENCODE_BASE_URL", "http://localhost:4096")).rstrip("/")
        pwd = password or os.environ.get("OPENCODE_PASSWORD", "")
        usr = username or os.environ.get("OPENCODE_USERNAME", "opencode")
        if not pwd:
            raise ValueError("OPENCODE_PASSWORD required. Set in .env or environment.")

        creds = base64.b64encode(f"{usr}:{pwd}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }
        self._default_model = model_id
        self._default_provider = provider_id
        self._session_id: str | None = None
        self._call_counter = 0

        # Expose messages interface matching anthropic.Anthropic().messages
        self.messages = self

    def create(
        self,
        model: str = "",
        system: str = "",
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> Response:
        """Mimics anthropic.messages.create() via OpenCode server.

        Uses ONE session per investigation. First call sends system + tools + alert.
        Subsequent calls send only the new tool result. Context accumulates in session.
        """
        messages = messages or []
        self._call_counter += 1

        # First call: full prompt. Subsequent: only new content.
        if self._session_id is None:
            self._session_id = self._create_session()
            prompt = self._build_prompt(system, messages, tools)
        else:
            prompt = self._build_incremental(messages)

        # Send to session (context accumulates across calls)
        raw_response = self._send_message(prompt)

        # Parse into Response object
        return self._parse_response(raw_response, has_tools=bool(tools))

    def cleanup(self):
        """Delete the session when done."""
        if self._session_id:
            self._delete_session(self._session_id)
            self._session_id = None

    def _build_prompt(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> str:
        """Build a single prompt from system + tools + conversation history."""
        parts: list[str] = []

        # System context
        if system:
            parts.append(system)
            parts.append("")

        # Tool definitions
        if tools:
            parts.append("## Available Tools\n")
            for tool in tools:
                name = tool["name"]
                desc = tool.get("description", "")
                props = tool.get("input_schema", {}).get("properties", {})
                required = tool.get("input_schema", {}).get("required", [])
                parts.append(f"### {name}")
                parts.append(desc)
                for pname, pdef in props.items():
                    req = " (required)" if pname in required else ""
                    parts.append(f"  - {pname}: {pdef.get('description', pdef.get('type', ''))}{req}")
                parts.append("")

            parts.append(
                "## IMPORTANT: Output Format\n"
                "You are in a tool-use simulation. You CANNOT call tools directly.\n"
                "Instead, you MUST output ONLY a JSON object (no other text) to request a tool call:\n\n"
                '{"action": "tool_call", "tool_name": "<name>", "tool_input": {...}, "reasoning": "why"}\n\n'
                "When you have enough evidence for a final answer, output:\n\n"
                '{"action": "respond", "text": "<your full investigation report>"}\n\n'
                "CRITICAL: Your entire response must be valid JSON. No markdown, no explanation, just the JSON object.\n"
                "The system will execute the tool and feed the result back to you.\n"
            )

        # Conversation history
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if isinstance(content, str):
                parts.append(f"[{role}]: {content}\n")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(f"[{role}]: {block['text']}\n")
                        elif block.get("type") == "tool_use":
                            parts.append(
                                f"[assistant tool_call]: {block['name']}({json.dumps(block.get('input', {}))[:300]})\n"
                            )
                        elif block.get("type") == "tool_result":
                            is_err = block.get("is_error", False)
                            status = "ERROR" if is_err else "OK"
                            content_str = str(block.get("content", ""))[:1500]
                            parts.append(f"[tool_result {status}]: {content_str}\n")

        return "\n".join(parts)

    def _build_incremental(self, messages: list[dict[str, Any]]) -> str:
        """Build prompt with only the latest tool result for subsequent turns.

        Since the session keeps context, we only need to send new information.
        """
        parts: list[str] = []

        # Find the last tool_result in messages
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        status = "ERROR" if block.get("is_error") else "OK"
                        parts.append(f"Tool result ({status}):\n{str(block.get('content', ''))[:2000]}")
                if parts:
                    break
            elif isinstance(content, str):
                parts.append(content)
                break

        parts.append(
            "\nBased on this result, output your next action as a JSON object. "
            "Either call another tool or provide your final respond."
        )
        return "\n".join(parts)

    def _create_session(self) -> str:
        """Create a new OpenCode session."""
        data = json.dumps({"title": f"sre-triage-{self._call_counter}"}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/session",
            data=data,
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        return body["id"]

    def _send_message(self, prompt: str) -> str:
        """Send a message to the OpenCode session and return the assistant's text response.

        OpenCode response structure:
          - POST returns the final assistant message metadata
          - Actual text is in GET /session/{id}/message → last assistant message → parts → type=text
        """
        payload = {
            "parts": [{"type": "text", "text": prompt}],
            "model": {
                "modelID": self._default_model,
                "providerID": self._default_provider,
            },
            "agent": "build",
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/session/{self._session_id}/message",
            data=data,
            headers=self._headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                resp.read()  # consume response (metadata only)
        except Exception:
            pass  # timeout — agent may still be running, poll below

        # Always poll for the actual text response from messages
        return self._get_last_assistant_text()

    def _get_last_assistant_text(self) -> str:
        """Get the text content from the last assistant message in the session."""
        req = urllib.request.Request(
            f"{self._base_url}/session/{self._session_id}/message",
            headers=self._headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                messages = json.loads(resp.read().decode())
        except Exception:
            return "[error: could not fetch session messages]"

        if not isinstance(messages, list):
            return "[error: unexpected message format]"

        # Find the last assistant message with text parts
        for msg in reversed(messages):
            info = msg.get("info", {})
            if info.get("role") != "assistant":
                continue
            # Text is in message-level parts, not info-level
            parts = msg.get("parts", [])
            text_parts = [p.get("text", "") for p in parts if p.get("type") == "text" and p.get("text")]
            if text_parts:
                return "\n".join(text_parts)

        return "[no assistant text found in session]"

    def _delete_session(self, session_id: str) -> None:
        """Delete a session."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/session/{session_id}",
                headers=self._headers,
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    def _parse_response(self, text: str, has_tools: bool) -> Response:
        """Parse the assistant's text response into a Response object.

        If the text contains a JSON block with action=tool_call, parse it as a tool use.
        Otherwise, treat it as a final text response.
        """
        usage = Usage(input_tokens=0, output_tokens=len(text) // 4)  # rough estimate

        if has_tools:
            # Try to extract JSON from the response
            tool_call = self._extract_tool_call(text)
            if tool_call:
                content = []
                reasoning = tool_call.get("reasoning", "")
                if reasoning:
                    content.append(TextBlock(text=reasoning))
                content.append(ToolUseBlock(
                    id=f"oc_call_{self._call_counter}",
                    name=tool_call.get("tool_name", ""),
                    input=tool_call.get("tool_input", {}),
                ))
                return Response(
                    content=content,
                    stop_reason="tool_use",
                    usage=usage,
                )

        # Final text response
        # If response contains action=respond JSON, extract the text
        respond_data = self._extract_respond(text)
        final_text = respond_data.get("text", text) if respond_data else text

        return Response(
            content=[TextBlock(text=final_text)],
            stop_reason="end_turn",
            usage=usage,
        )

    @staticmethod
    def _extract_tool_call(text: str) -> dict | None:
        """Extract a tool_call JSON from the response text."""
        # Try to find JSON block in markdown code fence
        import re
        json_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and data.get("action") == "tool_call":
                    return data
            except json.JSONDecodeError:
                continue

        # Try to parse the whole text as JSON
        try:
            data = json.loads(text.strip())
            if isinstance(data, dict) and data.get("action") == "tool_call":
                return data
        except json.JSONDecodeError:
            pass

        return None

    @staticmethod
    def _extract_respond(text: str) -> dict | None:
        """Extract a respond JSON from the response text."""
        import re
        json_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and data.get("action") == "respond":
                    return data
            except json.JSONDecodeError:
                continue

        try:
            data = json.loads(text.strip())
            if isinstance(data, dict) and data.get("action") == "respond":
                return data
        except json.JSONDecodeError:
            pass

        return None
