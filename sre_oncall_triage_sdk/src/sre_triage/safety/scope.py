"""Scope declaration and tracking.

Tracks what the agent declared as in-scope and out-of-scope,
and validates tool calls against the declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScopeTracker:
    """Tracks investigation scope and detects scope expansion."""

    clusters: list[str] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    _expansions: list[str] = field(default_factory=list)

    def declare(
        self,
        clusters: list[str] | None = None,
        namespaces: list[str] | None = None,
        services: list[str] | None = None,
        out_of_scope: list[str] | None = None,
    ) -> None:
        """Declare the investigation scope."""
        if clusters:
            self.clusters = clusters
        if namespaces:
            self.namespaces = namespaces
        if services:
            self.services = services
        if out_of_scope:
            self.out_of_scope = out_of_scope

    def check_query(self, query_text: str) -> str | None:
        """Check if a query references out-of-scope items."""
        query_lower = query_text.lower()
        for item in self.out_of_scope:
            if item.lower() in query_lower:
                self._expansions.append(
                    f"Query references out-of-scope item: '{item}'"
                )
                return f"WARNING: query references out-of-scope item '{item}'"
        return None

    @property
    def expansions(self) -> list[str]:
        return list(self._expansions)
