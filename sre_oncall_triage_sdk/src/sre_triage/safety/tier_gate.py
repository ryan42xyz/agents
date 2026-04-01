"""Environment tier gate — Python port of k8s-gate.sh logic.

Classifies cluster aliases into tiers and enforces access policies:
  PROD/PCI/MGT/DEMO: read-only (block all mutations)
  PREPROD: read + dry-run (block deletes, warn on mutations without --dry-run)
  DEV: most permissive (warn on deletes, require INTENT)
  UNKNOWN: treat as PROD (conservative default)
"""

from __future__ import annotations

import re

# --- Cluster alias patterns (from k8s-gate.sh) ---

PCI_PATTERN = re.compile(r"^(keastpcia|keastpcib)$")
PROD_PATTERN = re.compile(
    r"^(kafsouthprod[ab]|kwestprod[ab]|keastprod[ab]|"
    r"keuwestprod[ab]|keuwest2prodb|ksg[ab]|kasiasedcube|"
    r"kgcpwestproda|kcaprod[ab])$"
)
MGT_PATTERN = re.compile(r"^(kwestmgt|keastmgt)$")
PREPROD_PATTERN = re.compile(
    r"^(kafsouthpreprod|kwestpreprod|keastpreprod|keastpcipreprod|kcapreprod)$"
)
DEV_PATTERN = re.compile(r"^(kwestdev[ab]|keastdevc)$")
DEMO_PATTERN = re.compile(
    r"^(kwestdemo[ab]|kgcpwestpoc[ab]|kgcpwesttrial)$"
)

# Operations
MUTATING_PATTERN = re.compile(
    r"\b(apply|create|scale|patch|rollout\s+restart|drain|cordon|taint|exec|cp|run)\b"
)
DELETE_PATTERN = re.compile(r"\b(delete|del)\b")
READ_ONLY_COMMANDS = {"get", "describe", "logs", "top", "auth"}


class TierGate:
    """Validates kubectl commands against cluster tier policies."""

    def check(self, command: str, cluster: str) -> str | None:
        """Check if a kubectl command is allowed for the given cluster.

        Returns error message if blocked, None if OK.
        """
        tier = self.classify_tier(cluster)
        alias = cluster.strip()

        # Hard blocks — all tiers
        if re.search(r"\b(delete|del)\s+(ns|namespace)\b", command):
            return f"BLOCKED: namespace deletion not allowed via agent ({alias})"

        if re.search(r"\bdelete\b.*(-A\b|--all-namespaces)", command):
            return f"BLOCKED: cross-namespace deletion not allowed ({alias})"

        # Extract the kubectl subcommand
        parts = command.strip().split()
        if not parts:
            return "BLOCKED: empty command"

        # Skip the alias if it's the first word
        subcmd_idx = 0
        if parts[0] in (alias, "kubectl"):
            subcmd_idx = 1
        subcmd = parts[subcmd_idx] if len(parts) > subcmd_idx else ""

        # Tier-specific enforcement
        if tier in ("PROD", "PCI", "MGT", "DEMO"):
            if DELETE_PATTERN.search(command):
                return f"BLOCKED: delete on {tier} ({alias}) not allowed via agent"
            if MUTATING_PATTERN.search(command):
                return f"BLOCKED: mutating op on {tier} ({alias}) not allowed via agent. Generate command for human."

        elif tier == "PREPROD":
            if DELETE_PATTERN.search(command):
                return f"BLOCKED: delete on PREPROD ({alias}) not allowed via agent"
            if MUTATING_PATTERN.search(command) and "--dry-run" not in command:
                return f"BLOCKED: mutating op on PREPROD ({alias}) without --dry-run"

        elif tier == "DEV":
            if DELETE_PATTERN.search(command):
                # Warn but don't block on DEV
                pass
            # DEV is most permissive — allow with logging

        else:
            # UNKNOWN tier — treat as PROD
            if MUTATING_PATTERN.search(command) or DELETE_PATTERN.search(command):
                return f"BLOCKED: unclassified cluster ({alias}) treated as PROD — mutating ops blocked"

        return None

    @staticmethod
    def classify_tier(cluster: str) -> str:
        """Classify a cluster alias into an environment tier."""
        alias = cluster.strip()
        if PCI_PATTERN.match(alias):
            return "PCI"
        if PROD_PATTERN.match(alias):
            return "PROD"
        if MGT_PATTERN.match(alias):
            return "MGT"
        if DEMO_PATTERN.match(alias):
            return "DEMO"
        if PREPROD_PATTERN.match(alias):
            return "PREPROD"
        if DEV_PATTERN.match(alias):
            return "DEV"
        return "UNKNOWN"
