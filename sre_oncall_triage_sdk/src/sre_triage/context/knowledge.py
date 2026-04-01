"""Knowledge base loader — reads routing table, debug trees, and knowledge files.

Loads from the shared knowledge directory (../sre_oncall_triage_agent/knowledge/).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class KnowledgeLoader:
    """Loads and retrieves oncall knowledge files."""

    def __init__(self, knowledge_path: Path, facets_path: Path):
        self._knowledge_path = knowledge_path
        self._facets_path = facets_path
        self._index: list[dict[str, Any]] | None = None

    def load_routing_table(self) -> str:
        """Load the agent routing table for the system prompt."""
        path = self._knowledge_path / "agent-routing-table.md"
        if not path.exists():
            return "# Routing table not found — use FACETS-based investigation.\n"
        return path.read_text()

    def load_debug_tree(self, tree_name: str) -> str | None:
        """Load a specific debug tree by filename."""
        tree_dir = self._knowledge_path / "debug-trees"
        if not tree_dir.exists():
            return None

        # Try exact name, then with .md extension
        for candidate in [tree_name, f"{tree_name}.md", f"debug-tree-{tree_name}.md"]:
            path = tree_dir / candidate
            if path.exists():
                return path.read_text()
        return None

    def search(self, query: str, kind: str | None = None) -> str:
        """Search knowledge base by query terms and optional kind filter.

        Used by the lookup_knowledge tool.
        """
        if self._index is None:
            self._build_index()

        query_lower = query.lower()
        query_terms = query_lower.split()

        matches = []
        for entry in self._index:
            if kind and entry.get("kind") != kind:
                continue

            # Score by term match in summary, tags, filename
            score = 0
            searchable = f"{entry.get('summary', '')} {' '.join(entry.get('tags', []))} {entry['filename']}".lower()
            for term in query_terms:
                if term in searchable:
                    score += 1

            if score > 0:
                matches.append((score, entry))

        matches.sort(key=lambda x: -x[0])
        top = matches[:5]

        if not top:
            return f"No knowledge files matching '{query}' (kind={kind})"

        parts = []
        for _, entry in top:
            path = entry["path"]
            if path.exists():
                content = path.read_text()
                # Truncate long files
                if len(content) > 3000:
                    content = content[:3000] + "\n\n... (truncated)"
                parts.append(f"### {entry['filename']}\n\n{content}")
            else:
                parts.append(f"### {entry['filename']}\n\n(file not found)")

        return "\n\n---\n\n".join(parts)

    def _build_index(self) -> None:
        """Build an in-memory index of all knowledge files."""
        self._index = []
        for md_file in self._knowledge_path.rglob("*.md"):
            if md_file.name in ("README.md", "CLAUDE.md"):
                continue
            entry = self._parse_frontmatter(md_file)
            self._index.append(entry)

    def _parse_frontmatter(self, path: Path) -> dict[str, Any]:
        """Extract frontmatter metadata from a knowledge file."""
        text = path.read_text()
        entry: dict[str, Any] = {
            "path": path,
            "filename": path.name,
            "kind": "",
            "summary": "",
            "tags": [],
            "first_action": "",
        }

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.splitlines():
                line = line.strip()
                if line.startswith("kind:"):
                    entry["kind"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("summary:"):
                    entry["summary"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("first_action:"):
                    entry["first_action"] = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("tags:"):
                    # Simple tag parsing: tags: ["a", "b"] or tags: [a, b]
                    tag_str = line.split(":", 1)[1].strip()
                    entry["tags"] = [
                        t.strip().strip('"').strip("'")
                        for t in re.findall(r"[\w-]+", tag_str)
                    ]

        return entry
