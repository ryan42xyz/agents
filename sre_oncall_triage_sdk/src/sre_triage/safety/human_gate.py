"""Human gate — interactive confirmation for mutations.

In the SDK agent, this is a safety net. Since the agent is read-only by design,
this should rarely trigger. But it's here as a last line of defense.
"""

from __future__ import annotations

import sys


def confirm_action(action_description: str, command: str) -> bool:
    """Prompt the human operator for confirmation.

    Returns True if approved, False if denied.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"HUMAN GATE: {action_description}", file=sys.stderr)
    print(f"Command: {command}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    try:
        response = input("Approve? [y/N]: ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
